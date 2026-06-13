# Latency L3 — Reference-Safe Answer Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Build order: PLAN 4 of 4 — LAST** (L4 → L2 → L1 → **L3**). Build after L1 so the cache HIT path reuses the same SSE frame contract. Spec: `docs/superpowers/specs/completed/2026-06-10-answer-cache-latency-design.md`.

**Goal:** Serve a stored advisory for a verbatim-repeat, first-turn, reference-safe query in ~50ms — skipping classify + retrieve + generate + guard — without ever serving a stale or mismatched safety answer.

**Architecture:** New `services/answer_cache.py` (exact-normalized key over the English query + language + county + profile signature; Upstash-backed via existing `cache.cache_get/cache_set`; a Python port of the PWA `isCacheableAsReference` predicate). `routers/query.py` READs the cache after translate/before classify (first-turn only) and WRITEs after the final advisory is built (first-turn, not suppressed, reference-safe).

**Tech Stack:** Python/FastAPI SSE, Upstash Redis (best-effort), pytest (`asyncio.run`).

---

## Background for an engineer with zero context

- **Why safe:** the cache only ever stores **informational, rate-free, warning-free, non-time-sensitive** advisories (the `isCacheableAsReference` rules already trusted by the PWA offline layer, `frontend/src/lib/offlineTiering.js`), only for **first-turn** queries (no `session_history`), and only matches **exact-normalized** queries (a paraphrase MISSES). No rates/spray/timing answer is ever cached or matched fuzzily.
- **`backend/services/cache.py`:** `cache_get(key) -> dict | None` and `cache_set(key, value: dict, ttl=REDIS_TTL_SECONDS)`. Both are best-effort: when Upstash env is unset they no-op/return None. Reuse them.
- **`backend/routers/query.py` `query()` flow (current):** rate-limit → `sanitize` → `_trusted_rag_history` (→ `session_history`) → `get_profile` → `county_fips`/`rice_fields`/`language` → `en_message = await maybe_translate_query(...)` → `category = await classify_query(...)` → OOS early-return OR `event_stream` (StreamingResponse). Inside `event_stream`: `rag_task` → drain → `result, retrieved_chunks` → `if language=="es": result = await translate_advisory_to_es(result)` → `save_message` → final `data:` envelope frame → `[DONE]`.
- **`AdvisoryResponse`** (`backend/models/advisory.py`): `.model_dump()` → dict with at least `problem_summary`, `detailed_explanation`, `recommended_actions`, `key_points`, `products_rates`, `warnings`, `response_type`, `suppressed`, `confidence_score`, `escalation`.
- Tests: `backend/tests/`, run `cd backend && pytest tests/<file> -v`, async via `asyncio.run`. Stream tests use the `_patch_common`/`_collect`/`_blob` helpers (see `tests/test_query_heartbeat.py` / `tests/test_query_progress.py`).

## File Structure

- Create: `backend/services/answer_cache.py` — normalize, key, get/set, `is_cacheable_as_reference`.
- Modify: `backend/routers/query.py` — READ before classify, WRITE after final advisory, `_advisory_sse` helper for the hit path.
- Create: `backend/tests/test_answer_cache.py`.
- Modify: `backend/tests/test_query_progress.py` (or new `test_query_cache.py`) — hit/miss/eligibility integration.

---

### Task 1: answer_cache module (TDD)

**Files:**
- Create: `backend/services/answer_cache.py`
- Test: `backend/tests/test_answer_cache.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_answer_cache.py`:

```python
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import answer_cache as ac


def test_normalized_key_collapses_case_punctuation_whitespace():
    k1 = ac.answer_cache_key("Soybean seeding rate, NE Arkansas?", "en", "05055", None)
    k2 = ac.answer_cache_key("soybean   seeding rate NE arkansas", "en", "05055", None)
    assert k1 == k2


def test_key_differs_by_language_county_and_profile():
    base = ac.answer_cache_key("soybean seeding rate", "en", "05055", None)
    assert base != ac.answer_cache_key("soybean seeding rate", "es", "05055", None)
    assert base != ac.answer_cache_key("soybean seeding rate", "en", "05001", None)
    rf = [{"field_name": "north40", "last_flood_date": "2026-05-01"}]
    assert base != ac.answer_cache_key("soybean seeding rate", "en", "05055", rf)


def test_paraphrase_misses():
    k1 = ac.answer_cache_key("soybean seeding rate", "en", "05055", None)
    k2 = ac.answer_cache_key("how many soybean seeds per acre", "en", "05055", None)
    assert k1 != k2


def test_is_cacheable_only_clean_informational():
    good = {"response_type": "informational", "products_rates": [], "warnings": [],
            "problem_summary": "Soybeans are a legume grown widely.", "recommended_actions": ["Rotate crops yearly."],
            "key_points": [], "detailed_explanation": "", "suppressed": False}
    assert ac.is_cacheable_as_reference(good) is True

    assert ac.is_cacheable_as_reference({**good, "response_type": "diagnostic"}) is False
    assert ac.is_cacheable_as_reference({**good, "products_rates": [{"product": "X"}]}) is False
    assert ac.is_cacheable_as_reference({**good, "warnings": ["Wear gloves"]}) is False
    assert ac.is_cacheable_as_reference({**good, "recommended_actions": ["Spray today before wind picks up"]}) is False
    assert ac.is_cacheable_as_reference({**good, "suppressed": True}) is False


def test_get_set_roundtrip(monkeypatch):
    store = {}
    monkeypatch.setattr(ac, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(ac, "cache_set", lambda k, v, ttl=None: store.__setitem__(k, v))
    ac.set_cached_answer("answer:abc", {"problem_summary": "ok"})
    assert ac.get_cached_answer("answer:abc") == {"problem_summary": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_answer_cache.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `backend/services/answer_cache.py`:

```python
"""Exact-normalized, reference-safe advisory cache. First-turn only. Stores ONLY
informational, rate-free, warning-free, non-time-sensitive advisories so a cached
answer can never be a stale/mismatched safety reply. Python port of the PWA
predicate in frontend/src/lib/offlineTiering.js."""
import hashlib
import json
import re

import config
from services.cache import cache_get, cache_set

# Parity with offlineTiering.js TIME_SENSITIVE_RE.
_TIME_SENSITIVE_RE = re.compile(
    r"\b(spray|spraying|dicamba|engenia|xtendimax|tavium|application window|apply|"
    r"rate|oz/a|pt/a|inversion|burndown|pre-?harvest|window|today|forecast|wind)\b",
    re.IGNORECASE,
)


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").lower()).strip(" \t\n.?!,;:")


def _profile_sig(rice_fields) -> str:
    if not rice_fields:
        return ""
    items = sorted(
        (str(f.get("field_name", "")), str(f.get("last_flood_date", "")))
        for f in rice_fields
    )
    return hashlib.sha1(json.dumps(items).encode()).hexdigest()[:12]


def answer_cache_key(en_message: str, language: str, county_fips: str, rice_fields) -> str:
    raw = f"{_normalize(en_message)}|{language}|{county_fips}|{_profile_sig(rice_fields)}"
    return "answer:" + hashlib.sha1(raw.encode()).hexdigest()


def get_cached_answer(key: str):
    return cache_get(key)


def set_cached_answer(key: str, advisory: dict, ttl: int = config.REDIS_TTL_SECONDS) -> None:
    cache_set(key, advisory, ttl=ttl)


def _text_blob(advisory: dict) -> str:
    parts = [
        advisory.get("problem_summary") or "",
        advisory.get("detailed_explanation") or "",
        *(advisory.get("recommended_actions") or []),
        *(advisory.get("key_points") or []),
    ]
    return " ".join(parts)


def is_cacheable_as_reference(advisory: dict) -> bool:
    if not isinstance(advisory, dict):
        return False
    if advisory.get("suppressed"):
        return False
    if advisory.get("response_type") != "informational":
        return False
    if advisory.get("products_rates"):
        return False
    if advisory.get("warnings"):
        return False
    if _TIME_SENSITIVE_RE.search(_text_blob(advisory)):
        return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_answer_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/answer_cache.py backend/tests/test_answer_cache.py
git commit -m "feat(cache): reference-safe exact-normalized answer cache module"
```

---

### Task 2: query.py READ (cache hit short-circuit) (TDD)

**Files:**
- Modify: `backend/routers/query.py`
- Test: `backend/tests/test_query_cache.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_query_cache.py`:

```python
import asyncio
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _collect(resp):
    async def _run():
        return [c async for c in resp.body_iterator]
    return asyncio.run(_run())


def _blob(frames):
    return "".join(c.decode() if isinstance(c, (bytes, bytearray)) else c for c in frames)


def _patch_base(q, monkeypatch):
    async def fake_classify(*a, **k):
        return "IN_SCOPE_SOYBEANS:INFO"
    monkeypatch.setattr(q, "classify_query", fake_classify)
    monkeypatch.setattr(q, "get_profile", lambda sub: {"county_fips": "05055"})
    monkeypatch.setattr(q, "rate_limit_hit", lambda *a, **k: (True, 19))
    monkeypatch.setattr(q, "sanitize", lambda m: m)


def test_cache_hit_skips_rag(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)

    called = {"rag": 0}
    async def fake_rag(*a, **k):
        called["rag"] += 1
        raise AssertionError("run_rag_query must not be called on a cache hit")
    monkeypatch.setattr(q, "run_rag_query", fake_rag)

    cached = {"problem_summary": "Soybeans are a legume.", "_category": "IN_SCOPE_SOYBEANS:INFO"}
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: dict(cached))
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    req = q.QueryRequest(message="soybean facts", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))
    assert called["rag"] == 0
    assert '"problem_summary": "Soybeans are a legume."' in blob
    assert '"_category"' not in blob  # internal field stripped from the frame
    assert "[DONE]" in blob


def test_cache_not_read_with_session_history(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)
    seen = {"get": 0}
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: seen.__setitem__("get", seen["get"] + 1) or None)

    class _Res:
        confidence_score = 0.9
        suppressed = False
        escalation = None
        def model_dump(self):
            return {"problem_summary": "x", "response_type": "informational",
                    "products_rates": [], "warnings": [], "suppressed": False}
    async def fake_rag(*a, **k):
        return (_Res(), [])
    monkeypatch.setattr(q, "run_rag_query", fake_rag)
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    req = q.QueryRequest(message="soybean facts", language="en",
                         session_history=[{"role": "user", "content": "hi"},
                                          {"role": "assistant", "content": "hello"}])
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    _blob(_collect(resp))
    assert seen["get"] == 0  # never read the cache on a follow-up
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_query_cache.py -v`
Expected: FAIL — `q.answer_cache` is not imported and there is no hit short-circuit.

- [ ] **Step 3: Implement the READ + hit stream**

In `backend/routers/query.py`:
- Add import near the other service imports: `from services import answer_cache`.
- Add a module-level helper for the hit/stream frame (place beside the other module helpers):

```python
def _advisory_sse(advisory: dict, message_id, category):
    """Build the SSE generator for a ready advisory dict (cache hit). Same frame
    shape as the miss path so the frontend consumer is unchanged."""
    async def _gen():
        yield ": keepalive\n\n"
        envelope = {"advisory": advisory, "message_id": message_id, "category": category}
        yield f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return _gen()
```

- In `query()`, AFTER `en_message = await maybe_translate_query(...)` and BEFORE
  `category = await classify_query(...)`, add the READ:

```python
    cache_key = None
    if not session_history:
        cache_key = answer_cache.answer_cache_key(en_message, language, county_fips, rice_fields)
        cached = answer_cache.get_cached_answer(cache_key)
        if cached:
            cached = dict(cached)
            hit_category = cached.pop("_category", None)
            message_id = None
            if req.session_id:
                try:
                    save_message(req.session_id, user["sub"], "user", req.message, "text")
                    row = save_message(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(cached, ensure_ascii=False), "advisory",
                    )
                    message_id = row["id"]
                except Exception:
                    logger.exception("Failed to persist cached advisory")
            return StreamingResponse(
                _advisory_sse(cached, message_id, hit_category),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
```

(`cache_key` is computed here so the WRITE path, Task 3, can reuse it. When
`session_history` is non-empty, `cache_key` stays `None` → no read, no write.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_query_cache.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_cache.py
git commit -m "feat(query): serve reference-safe first-turn cache hits"
```

---

### Task 3: query.py WRITE (cache eligible answers) (TDD)

**Files:**
- Modify: `backend/routers/query.py` — `event_stream`
- Test: `backend/tests/test_query_cache.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_query_cache.py`:

```python
def _streamy_result(dump):
    class _Res:
        confidence_score = 0.9
        suppressed = dump.get("suppressed", False)
        escalation = None
        def model_dump(self):
            return dict(dump)
    return _Res()


def test_cacheable_answer_is_written(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: None)

    written = {}
    monkeypatch.setattr(q.answer_cache, "set_cached_answer", lambda key, val, **k: written.update({key: val}))
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    dump = {"problem_summary": "Soybeans are a legume.", "response_type": "informational",
            "products_rates": [], "warnings": [], "recommended_actions": ["Rotate crops."],
            "key_points": [], "detailed_explanation": "", "suppressed": False}
    async def fake_rag(*a, **k):
        return (_streamy_result(dump), [])
    monkeypatch.setattr(q, "run_rag_query", fake_rag)

    req = q.QueryRequest(message="soybean facts", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    _blob(_collect(resp))
    assert len(written) == 1
    (val,) = written.values()
    assert val["_category"] == "IN_SCOPE_SOYBEANS:INFO"


def test_rate_bearing_answer_not_written(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: None)
    written = {}
    monkeypatch.setattr(q.answer_cache, "set_cached_answer", lambda key, val, **k: written.update({key: val}))
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    dump = {"problem_summary": "Apply N.", "response_type": "informational",
            "products_rates": [{"product": "Urea", "rate": "100 lb/ac"}], "warnings": [],
            "recommended_actions": [], "key_points": [], "detailed_explanation": "", "suppressed": False}
    async def fake_rag(*a, **k):
        return (_streamy_result(dump), [])
    monkeypatch.setattr(q, "run_rag_query", fake_rag)

    req = q.QueryRequest(message="how much urea", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    _blob(_collect(resp))
    assert written == {}  # products_rates present -> never cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_query_cache.py -k written -v`
Expected: FAIL — no WRITE logic yet.

- [ ] **Step 3: Implement the WRITE**

In `event_stream` (inside `query()`), after the final advisory is ready. The
eligibility is judged on the **English** advisory (the English `_TIME_SENSITIVE_RE`),
so capture it before the ES translation:

- Right after `result, retrieved_chunks = rag_task.result()`, add:
  ```python
  en_advisory_dump = result.model_dump()
  ```
- Leave the existing `if language == "es": result = await translate_advisory_to_es(result, ...)` and `save_message` block as-is.
- After the `save_message` block (still inside the `try`, before building the final
  `envelope`), add:
  ```python
  if cache_key and not getattr(result, "suppressed", False) and answer_cache.is_cacheable_as_reference(en_advisory_dump):
      final_dump = result.model_dump()
      answer_cache.set_cached_answer(cache_key, {**final_dump, "_category": category})
  ```

`cache_key` is captured from the enclosing `query()` scope (set in Task 2; `None`
when `session_history` is non-empty → never writes). The stored value is the
**user-facing** advisory (ES if translated) plus `_category`; eligibility is judged
on the EN text.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_query_cache.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_cache.py
git commit -m "feat(query): write reference-safe advisories to the answer cache"
```

---

### Task 4: Regression + manual

- [ ] **Step 1: Backend suite**

Run: `cd backend && pytest tests/ -k "query or cache or rag" -v`
Expected: PASS — including the L1 progress tests (the miss path still streams
progress; the hit path streams a single advisory frame with no progress stages).

- [ ] **Step 2: Manual (optional, running app + Upstash configured)**

Submit the SAME informational query twice (first turn, no rates/warnings): the
second returns in <100ms (no progress stages — instant advisory). Submit a query
whose answer carries a rate or a spray/timing term: it is regenerated every time
(never cached). A follow-up (with history) is never served from cache.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "test(l3): regression fixups for answer cache"
```

---

## Self-Review (completed)

- **Spec coverage:** exact-normalized key incl. lang/county/profile (Task 1) ✓; `is_cacheable_as_reference` JS port (Task 1) ✓; first-turn-only read+write via `cache_key` gate (Tasks 2–3) ✓; hit short-circuit skipping classify/retrieve/generate/guard, same SSE frame shape (Task 2) ✓; eligibility judged on EN, store user-facing incl. `_category`, never suppressed/rate/warning/time-sensitive (Task 3) ✓; Redis-down best-effort via existing cache no-op ✓; rate-limit stays before cache (unchanged, Task 2 inserts after it) ✓.
- **Placeholders:** none.
- **Type consistency:** `answer_cache_key`, `get_cached_answer`, `set_cached_answer`, `is_cacheable_as_reference` signatures match between module (Task 1) and router calls (Tasks 2–3); stored value carries `_category`, stripped before the hit frame (Task 2) and added on write (Task 3); `cache_key` name consistent across READ and WRITE.
```
