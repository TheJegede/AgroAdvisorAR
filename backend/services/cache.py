import json
import logging
import threading
import time
from upstash_redis import Redis
import config

logger = logging.getLogger(__name__)

_redis: Redis | None = None

# Process-local fixed-window fallback for rate limiting when Redis is
# unreachable. Keeps the per-user cap enforced during an outage instead of
# failing open (which would expose unlimited LLM calls). Per-process only, so
# the effective cap is per worker — acceptable as a degraded abuse cap.
_fallback_lock = threading.Lock()
_fallback_counters: dict[str, tuple[int, float]] = {}  # key -> (count, window_start)


def _fallback_rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = time.time()
    with _fallback_lock:
        count, window_start = _fallback_counters.get(key, (0, now))
        if now - window_start >= window_seconds:
            count, window_start = 0, now
        count += 1
        _fallback_counters[key] = (count, window_start)
    return count <= limit, max(0, limit - count)


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
        logger.exception("Redis cache_get failed for key %s", key)
        return None


def cache_set(key: str, value: dict, ttl: int = config.REDIS_TTL_SECONDS) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl)
    except Exception:
        logger.exception("Redis cache_set failed for key %s", key)


def rate_limit_hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Increment a fixed-window counter for `key`. Returns (allowed, remaining).

    Uses Redis when available; falls back to a process-local fixed-window
    counter when Redis is unreachable so the cap stays enforced during an
    outage (does NOT fail open). Note: fixed-window, not sliding — bursts at a
    window boundary can briefly exceed the nominal per-window count.
    """
    client = _get_client()
    if client is None:
        return _fallback_rate_limit(key, limit, window_seconds)
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        remaining = max(0, limit - count)
        return count <= limit, remaining
    except Exception:
        logger.exception("Redis rate_limit_hit failed for key %s — using local fallback", key)
        return _fallback_rate_limit(key, limit, window_seconds)
