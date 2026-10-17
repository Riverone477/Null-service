import json
import re
import time
from typing import Optional, Tuple

from redis.asyncio import Redis

from app.utils._redis import get_redis_client
from app.utils.config import settings


PHONE_RATE_PREFIX = "rl:phone:"

# Progressive cooldowns to prevent permanent lockout from repeated failures
COOLDOWNS = [
    (5, 60),        # 5 failures -> 1 minute
    (10, 5 * 60),   # 10 failures -> 5 minutes
    (15, 15 * 60),  # 15 failures -> 15 minutes
    (20, 60 * 60),  # 20 failures -> 1 hour
]


def canonicalize_phone(phone: str) -> str:
    if not phone:
        return ""
    p = phone.strip()
    if p.startswith("+"):
        p = p[1:]
    # remove non-digit chars if any
    p = re.sub(r"\D", "", p)
    return p


async def phone_limit_key(phone: str, redis: Optional[Redis] = None) -> str:
    return f"{PHONE_RATE_PREFIX}{canonicalize_phone(phone)}"


class PhoneRateLimiter:
    def __init__(
        self,
        redis: Optional[Redis] = None,
        window_seconds: Optional[int] = None,
        max_in_window: Optional[int] = None,
    ):
        self.redis = redis
        self.window_seconds = (
            window_seconds if window_seconds is not None else settings.phone_rate_window_seconds
        )
        self.max_in_window = (
            max_in_window if max_in_window is not None else settings.phone_rate_max_in_window
        )

    async def check_and_inc(self, phone: str) -> Tuple[bool, int]:
        if self.redis is None:
            self.redis = get_redis_client()
        k = f"{PHONE_RATE_PREFIX}{canonicalize_phone(phone)}"
        now = int(time.time())
        member = f"{now}:{time.time_ns()}"
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(k, 0, now - self.window_seconds)
        pipe.zadd(k, {member: now})
        pipe.zcard(k)
        pipe.expire(k, self.window_seconds + 60)
        _, _, count, _ = await pipe.execute()
        allowed = int(count) <= self.max_in_window
        return allowed, int(count)

    async def record_failure(self, phone: str) -> Tuple[bool, int]:
        if self.redis is None:
            self.redis = get_redis_client()
        k = f"phone:fail:{canonicalize_phone(phone)}"
        now = int(time.time())
        pipe = self.redis.pipeline()
        pipe.incr(k)
        pipe.expire(k, 24 * 60 * 60)
        cnt = (await pipe.execute())[1]
        cnt_int = int(cnt)
        # apply progressive cooldown
        for threshold, cd in COOLDOWNS:
            if cnt_int >= threshold:
                cd_key = f"phone:cooldown:{canonicalize_phone(phone)}"
                await self.redis.set(cd_key, "1", ex=cd)
                break
        return True, cnt_int

    async def clear_failures(self, phone: str) -> None:
        if self.redis is None:
            self.redis = get_redis_client()
        c = canonicalize_phone(phone)
        await self.redis.delete(f"phone:fail:{c}", f"phone:cooldown:{c}")

    async def is_cooldown(self, phone: str) -> Tuple[bool, int]:
        if self.redis is None:
            self.redis = get_redis_client()
        c = canonicalize_phone(phone)
        cd_key = f"phone:cooldown:{c}"
        ttl = await self.redis.ttl(cd_key)
        return ttl > 0, max(0, ttl)
