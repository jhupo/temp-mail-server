from __future__ import annotations

import threading
import time
from collections import defaultdict

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ModuleNotFoundError:
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass

from app.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._memory_bucket: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self._lock = threading.Lock()
        if settings.redis_url and Redis is not None:
            try:
                self._redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1)
                self._redis.ping()
            except RedisError:
                self._redis = None

    def check_new_mailbox(self, ip: str) -> tuple[bool, int]:
        limit = max(settings.rate_limit_new_per_minute, 1)
        key = f"ratelimit:new:{ip}"
        ttl = 60
        if self._redis is not None:
            try:
                with self._redis.pipeline() as pipe:
                    pipe.incr(key, 1)
                    pipe.expire(key, ttl, nx=True)
                    result = pipe.execute()
                current = int(result[0])
                if current > limit:
                    return False, ttl
                return True, ttl
            except RedisError:
                pass
        return self._check_memory(key, limit, ttl)

    def _check_memory(self, key: str, limit: int, ttl: int) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            count, expires_at = self._memory_bucket[key]
            if now >= expires_at:
                count = 0
                expires_at = now + ttl
            count += 1
            self._memory_bucket[key] = (count, expires_at)
            retry_after = max(int(expires_at - now), 1)
            return count <= limit, retry_after


limiter = RateLimiter()
