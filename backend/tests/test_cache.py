# backend/tests/test_cache.py
"""F6 — rate limiter must NOT fail open on a Redis outage; a process-local
fixed-window fallback keeps the per-user cap enforced."""
import importlib
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_rate_limit_fallback_enforces_cap_when_redis_down(monkeypatch):
    cache = importlib.import_module("services.cache")
    monkeypatch.setattr(cache, "_get_client", lambda: None)
    cache._fallback_counters.clear()

    key = "query_throttle:user-x"
    results = [cache.rate_limit_hit(key, 3, 3600) for _ in range(4)]
    allowed = [a for a, _ in results]
    # First 3 allowed, 4th blocked — not unlimited (would be all True if fail-open).
    assert allowed == [True, True, True, False]


def test_rate_limit_fallback_resets_after_window(monkeypatch):
    cache = importlib.import_module("services.cache")
    monkeypatch.setattr(cache, "_get_client", lambda: None)
    cache._fallback_counters.clear()

    key = "query_throttle:user-y"
    assert cache.rate_limit_hit(key, 1, 1)[0] is True
    assert cache.rate_limit_hit(key, 1, 1)[0] is False
    time.sleep(1.05)
    assert cache.rate_limit_hit(key, 1, 1)[0] is True  # window rolled over


def test_rate_limit_fallback_on_redis_error(monkeypatch):
    cache = importlib.import_module("services.cache")

    class BoomClient:
        def incr(self, *_a):
            raise RuntimeError("redis down")

    monkeypatch.setattr(cache, "_get_client", lambda: BoomClient())
    cache._fallback_counters.clear()

    key = "query_throttle:user-z"
    results = [cache.rate_limit_hit(key, 2, 3600)[0] for _ in range(3)]
    assert results == [True, True, False]
