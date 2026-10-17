import json
import secrets
import time
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from app.utils._redis import get_redis_client


JTI_PREFIX = "jti:login:"


def _jti_key(jti: str) -> str:
    return f"{JTI_PREFIX}{jti}"


async def issue_login_jti(
    redis: Optional[Redis] = None,
    *,
    user_id: str,
    phone_number: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Mint a device login JTI.

    A JTI has no TTL: it lives until it is used. Used JTIs are deleted, not
    marked, so the same id is never useful again. Abandoned (orphaned) JTIs
    can linger, but they are rare (one per device that never signs in again)
    and are cleared by a Redis flush/restart.
    """
    if redis is None:
        redis = get_redis_client()

    jti = secrets.token_urlsafe(32)
    payload = {
        "jti": jti,
        "user_id": user_id,
        "phone_number": phone_number or "",
        "issued_at": int(time.time()),
    }
    await redis.set(_jti_key(jti), json.dumps(payload))
    return jti


async def get_login_jti(jti: str, redis: Optional[Redis] = None) -> Optional[Dict[str, Any]]:
    if redis is None:
        redis = get_redis_client()
    data = await redis.get(_jti_key(jti))
    if not data:
        return None
    try:
        return json.loads(data)
    except (TypeError, ValueError):
        return None


# Consume is the point of no return: the JTI is DELETED. A missing key means
# already-used (or never valid), so replay is impossible. Atomic, so concurrent
# requests can never both consume one JTI.
_CONSUME_LUA = """
local key = KEYS[1]
local data = redis.call('GET', key)
if not data then
  return {0, 'not_found'}
end
local obj = cjson.decode(data)
redis.call('DEL', key)
return {1, obj.user_id, obj.phone_number or ''}
"""


async def consume_login_jti_atomic(
    jti: str,
    *,
    redis: Optional[Redis] = None,
) -> Dict[str, Any]:
    if redis is None:
        redis = get_redis_client()
    script = redis.register_script(_CONSUME_LUA)
    res = await script(keys=[_jti_key(jti)])
    if not res or int(res[0]) != 1:
        reason = res[1] if len(res) > 1 else "invalid"
        raise ValueError(reason)
    return {"user_id": res[1], "phone_number": res[2] if len(res) > 2 else ""}


async def revoke_login_jti(jti: str, redis: Optional[Redis] = None) -> None:
    """Kill a JTI without using it (e.g. logout/compromise)."""
    if redis is None:
        redis = get_redis_client()
    await redis.delete(_jti_key(jti))
