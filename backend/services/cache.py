import json
from upstash_redis import Redis
import config

_redis: Redis | None = None


def _get_client() -> Redis | None:
    global _redis
    if _redis is None and config.UPSTASH_REDIS_REST_URL:
        _redis = Redis(
            url=config.UPSTASH_REDIS_REST_URL,
            token=config.UPSTASH_REDIS_REST_TOKEN,
        )
    return _redis


def cache_get(key: str) -> dict | None:
    client = _get_client()
    if client is None:
        return None
    try:
        val = client.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_set(key: str, value: dict, ttl: int = config.REDIS_TTL_SECONDS) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


def rate_limit_hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Increment a sliding counter for `key`. Returns (allowed, remaining).

    Fail-open: if Redis is unreachable, allow the request (returns (True, limit)).
    Suitable for non-critical limits like feedback throttling. Do not use for
    security-critical rate limits without a fallback.
    """
    client = _get_client()
    if client is None:
        return True, limit
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        remaining = max(0, limit - count)
        return count <= limit, remaining
    except Exception:
        return True, limit
