import json
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from redis.asyncio import Redis

from app.utils._redis import get_redis_client
from app.utils.config import settings

# Application-wide bcrypt admission control, shared across every FastAPI
# worker/instance through Redis. No process-local semaphore participates in
# the global limit (a local one may still cap per-worker work, but is not the
# source of truth), so N workers cannot each run MAX jobs. All tunables are
# read from env (see app/utils/config.py).

BCRYPT_MAX_CONCURRENCY = settings.bcrypt_max_concurrency
QUEUE_MAX_SIZE = settings.login_queue_max_size
TICKET_TTL_SECONDS = settings.login_ticket_ttl_seconds       # how long a queued ticket stays valid
PERMIT_TTL_SECONDS = settings.login_permit_ttl_seconds       # how long a claimed permit may be used
OUTSTANDING_TICKETS_PER_SOURCE = settings.login_outstanding_tickets_per_source
TICKETS_CREATED_PER_SOURCE_WINDOW = settings.login_tickets_per_source_window
TICKETS_CREATED_PER_SOURCE_TTL = settings.login_tickets_per_source_ttl
ACTIVE_KEY_TTL = settings.login_active_key_ttl

KEY_ACTIVE = "bcrypt:login:active"
KEY_QUEUE = "bcrypt:login:queue"
KEY_PERMIT_PREFIX = "bcrypt:login:permit:"
KEY_TICKET_PREFIX = "bcrypt:login:ticket:"
KEY_CREATED_PREFIX = "bcrypt:login:created:"
KEY_OUTSTANDING_PREFIX = "bcrypt:login:outstanding:"


def _ticket_key(tid: str) -> str:
    return f"{KEY_TICKET_PREFIX}{tid}"


def _permit_key(pid: str) -> str:
    return f"{KEY_PERMIT_PREFIX}{pid}"


def _created_key(src: str) -> str:
    return f"{KEY_CREATED_PREFIX}{src}"


def _outstanding_key(src: str) -> str:
    return f"{KEY_OUTSTANDING_PREFIX}{src}"


# Atomic bounded enqueue: reject if the FIFO already holds max_size entries.
# Doing LLEN then RPUSH as two round-trips would let concurrent callers all
# pass the check and overshoot the cap, so the compare-and-push is one script.
_ENQUEUE_LUA = """
local queue = KEYS[1]
local ticket_key = KEYS[2]
local outstanding_key = KEYS[3]
local max_size = tonumber(ARGV[1])
local ticket_ttl = tonumber(ARGV[2])
local tid = ARGV[3]
local ticket_json = ARGV[4]

if redis.call('LLEN', queue) >= max_size then
  return 0
end
redis.call('SET', ticket_key, ticket_json, 'EX', ticket_ttl)
redis.call('INCR', outstanding_key)
redis.call('EXPIRE', outstanding_key, ticket_ttl + 10)
redis.call('RPUSH', queue, tid)
return 1
"""


async def create_ticket(source_id: str, *, redis: Optional[Redis] = None) -> Dict[str, Any]:
    """Create a bounded, expiring queue ticket for a source.

    Tickets are cheap identifiers, not reserved bcrypt slots. A ticket only
    lets the client poll for eligibility; capacity is granted later, and only
    if this ticket reaches the head of the FIFO queue. The queue is capped at
    LOGIN_QUEUE_MAX_SIZE so concurrent Flow 2 traffic cannot fill it forever.
    """
    if redis is None:
        redis = get_redis_client()

    created = int(await redis.incr(_created_key(source_id)))
    if created == 1:
        await redis.expire(_created_key(source_id), TICKETS_CREATED_PER_SOURCE_TTL)
    if created > TICKETS_CREATED_PER_SOURCE_WINDOW:
        raise HTTPException(status_code=429, detail="Too many login attempts, try again later")

    outstanding = int(await redis.get(_outstanding_key(source_id)) or 0)
    if outstanding >= OUTSTANDING_TICKETS_PER_SOURCE:
        raise HTTPException(status_code=429, detail="Too many outstanding login requests")

    tid = secrets.token_urlsafe(24)
    now = int(time.time())
    ticket = {
        "tid": tid,
        "source": source_id,
        "created_at": now,
        "expires_at": now + TICKET_TTL_SECONDS,
    }
    script = redis.register_script(_ENQUEUE_LUA)
    ok = await script(
        keys=[KEY_QUEUE, _ticket_key(tid), _outstanding_key(source_id)],
        args=[QUEUE_MAX_SIZE, TICKET_TTL_SECONDS + 5, tid, json.dumps(ticket)],
    )
    if not ok:
        raise HTTPException(status_code=429, detail="Login queue is full")
    return ticket


async def get_ticket(tid: str, redis: Optional[Redis] = None) -> Optional[Dict[str, Any]]:
    if redis is None:
        redis = get_redis_client()
    data = await redis.get(_ticket_key(tid))
    if not data:
        return None
    try:
        return json.loads(data)
    except (TypeError, ValueError):
        return None


def _queue_position_lua() -> str:
    return """
local queue = KEYS[1]
local tid = ARGV[1]
local idx = redis.call('LPOS', queue, tid)
if idx == false then
  return -1
end
return idx
"""


async def queue_position(tid: str, redis: Optional[Redis] = None) -> int:
    if redis is None:
        redis = get_redis_client()
    try:
        idx = await redis.lpos(KEY_QUEUE, tid)
    except Exception:
        return -1
    return -1 if idx is None else int(idx)


async def release_ticket(tid: str, redis: Optional[Redis] = None) -> None:
    """Drop a ticket the client no longer needs and free its per-source slot."""
    if redis is None:
        redis = get_redis_client()
    data = await redis.get(_ticket_key(tid))
    pipe = redis.pipeline()
    pipe.delete(_ticket_key(tid))
    pipe.lrem(KEY_QUEUE, 0, tid)
    await pipe.execute()
    if data:
        try:
            source = json.loads(data).get("source")
            if source:
                await redis.decr(_outstanding_key(source))
        except (TypeError, ValueError):
            pass


async def release_ticket_source(source: Optional[str], redis: Optional[Redis] = None) -> None:
    """Free the per-source outstanding slot for an already-consumed ticket."""
    if not source:
        return
    if redis is None:
        redis = get_redis_client()
    try:
        script = redis.register_script(
            """
            local current = tonumber(redis.call('GET', KEYS[1]) or 0)
            if current <= 0 then
              return 0
            end
            return redis.call('DECR', KEYS[1])
            """
        )
        await script(keys=[_outstanding_key(source)])
    except Exception:
        pass


# Atomically grant a permit iff the caller's ticket is the FIFO head and
# there is free capacity. Increments the shared active counter in the same
# script, so concurrent claims can never oversubscribe the limit.
_CLAIM_LUA = """
local active_key = KEYS[1]
local queue_key = KEYS[2]
local permit_key = KEYS[3]
local ticket_key = KEYS[4]
local active = tonumber(redis.call('GET', active_key) or 0)
local max_conc = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local permit_ttl = tonumber(ARGV[3])
local pid = ARGV[4]
local tid = ARGV[5]
local ticket_prefix = ARGV[7]

-- Prune stale tickets from the head so expired/missing entries never block
-- the queue or permanently occupy queue capacity. Bounded to avoid long work.
local pruned = 0
while pruned < 128 do
  local h = redis.call('LINDEX', queue_key, 0)
  if not h then
    break
  end
  local hdata = redis.call('GET', ticket_prefix .. h)
  if not hdata then
    redis.call('LPOP', queue_key)
    pruned = pruned + 1
  else
    local hobj = cjson.decode(hdata)
    if hobj.expires_at and tonumber(hobj.expires_at) < now then
      redis.call('LPOP', queue_key)
      redis.call('DEL', ticket_prefix .. h)
      pruned = pruned + 1
    else
      break
    end
  end
end

if active >= max_conc then
  return {0, -1}
end

if tid ~= '' then
  local head = redis.call('LINDEX', queue_key, 0)
  if head ~= tid then
    return {2, -1}
  end
  local tdata = redis.call('GET', ticket_key)
  if not tdata then
    redis.call('LREM', queue_key, 0, tid)
    return {3, -1}
  end
  local ticket = cjson.decode(tdata)
  if ticket.expires_at and tonumber(ticket.expires_at) < now then
    redis.call('LREM', queue_key, 0, tid)
    redis.call('DEL', ticket_key)
    return {3, -1}
  end
  redis.call('LPOP', queue_key)
  redis.call('DEL', ticket_key)
else
  if redis.call('LLEN', queue_key) > 0 then
    return {2, -1}
  end
end

local permit = cjson.encode({pid=pid, tid=tid, created_at=now, expires_at=now+permit_ttl})
redis.call('SET', permit_key, permit, 'EX', permit_ttl)
redis.call('INCR', active_key)
redis.call('EXPIRE', active_key, ARGV[6])
return {1, pid}
"""


async def claim_permit(
    *,
    ticket_id: str = "",
    redis: Optional[Redis] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Attempt to claim a short-lived single-use bcrypt permit.

    Returns (code, info):
      1 = granted (info["permit_id"])
      2 = not eligible yet: the ticket is valid but not at the head / no slot
      0 = no slot available (at capacity)
      3 = ticket invalid/expired
    """
    if redis is None:
        redis = get_redis_client()
    script = redis.register_script(_CLAIM_LUA)
    now = int(time.time())
    pid = secrets.token_urlsafe(24)
    res = await script(
        keys=[
            KEY_ACTIVE,
            KEY_QUEUE,
            _permit_key(pid),
            _ticket_key(ticket_id) if ticket_id else _ticket_key(""),
        ],
        args=[
            BCRYPT_MAX_CONCURRENCY,
            now,
            PERMIT_TTL_SECONDS,
            pid,
            ticket_id,
            ACTIVE_KEY_TTL,
            KEY_TICKET_PREFIX,
        ],
    )
    code = int(res[0]) if res else 0
    info: Dict[str, Any] = {"retry_after": 5}
    if code == 1:
        info = {"permit_id": res[1], "retry_after": 0}
    return code, info


# A permit is single-use: consuming it flips a flag so a replay sees 'used'.
_CONSUME_PERMIT_LUA = """
local data = redis.call('GET', KEYS[1])
if not data then
  return {0, 'not_found'}
end
local obj = cjson.decode(data)
if obj.used == true then
  return {0, 'used'}
end
if obj.expires_at and tonumber(obj.expires_at) < tonumber(ARGV[1]) then
  return {0, 'expired'}
end
obj.used = true
obj.used_at = tonumber(ARGV[1])
redis.call('SET', KEYS[1], cjson.encode(obj), 'EX', 5)
return {1, 'ok'}
"""


async def consume_permit(pid: str, redis: Optional[Redis] = None) -> Dict[str, Any]:
    if redis is None:
        redis = get_redis_client()
    script = redis.register_script(_CONSUME_PERMIT_LUA)
    now = int(time.time())
    res = await script(keys=[_permit_key(pid)], args=[now])
    if not res or int(res[0]) != 1:
        reason = res[1] if len(res) > 1 else "invalid"
        raise ValueError(reason)
    return {"permit_id": pid}


async def release_active(redis: Optional[Redis] = None) -> None:
    """Free one bcrypt slot. Must run on success, failure, cancel or exception."""
    if redis is None:
        redis = get_redis_client()
    try:
        script = redis.register_script(
            """
            local current = tonumber(redis.call('GET', KEYS[1]) or 0)
            if current <= 0 then
              return 0
            end
            return redis.call('DECR', KEYS[1])
            """
        )
        await script(keys=[KEY_ACTIVE])
    except Exception:
        pass
