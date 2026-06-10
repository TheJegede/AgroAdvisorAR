# Reference-Safe Answer Cache (Latency Lever 3)

**Date:** 2026-06-10
**Status:** Design approved, pending spec review
**Lever:** Answer-latency lever 3 (repeat queries ~2.8s → ~50ms).

## Problem

Every `/api/v1/query` re-pays the full 4-LLM critical path (~2.8s), even for an
identical repeat question. The Upstash 6h cache (`services/cache.py`) currently
caches only SSURGO/NOAA context (`services/context.py`) — **nothing on the
answer path**. Common first-turn FAQs ("soybean seeding rate in NE Arkansas")
are regenerated from scratch every time.

## Goal & non-goals

**Goal:** serve a stored advisory for a verbatim repeat query in ~50ms, skipping
classify + retrieve + generate + guard — **without ever serving a stale or
mismatched safety answer.**

**Non-goals (YAGNI):**
- No semantic/embedding match — exact normalized only (a near-but-different query
  must MISS, never return a subtly-wrong cached rate). Clean matcher seam left
  for a future semantic swap, but not built now.
- No caching of conversational follow-ups (answer depends on prior turns).
- No caching of time-sensitive/safety advisories (rates, warnings, spray timing).

## Safety model

Two gates, both required to cache:

1. **First-turn only:** cache READ and WRITE happen only when `session_history`
   is empty. A follow-up's answer depends on context from earlier turns.
2. **Reference-safe only:** WRITE only when the advisory passes
   `is_cacheable_as_reference` — a server-side port of the existing PWA predicate
   `frontend/src/lib/offlineTiering.js`, identical rules:
   - `response_type == "informational"` (else skip)
   - `products_rates` empty
   - `warnings` empty
   - no time-sensitive term in problem_summary/detailed_explanation/
     recommended_actions/key_points (regex parity with the JS
     `TIME_SENSITIVE_RE`: spray|dicamba|engenia|xtendimax|tavium|apply|rate|
     oz/a|pt/a|inversion|burndown|pre-harvest|window|today|forecast|wind)
   - suppressed advisories never cached.

This reuses the offline=abstention tiering already trusted in production.

## Architecture

### `services/answer_cache.py` (new)

```python
def _normalize(q: str) -> str:
    # lowercase, collapse internal whitespace, strip surrounding punctuation
    return re.sub(r"\s+", " ", q.lower()).strip(" \t\n.?!,;:")

def _profile_sig(rice_fields: list[dict] | None) -> str:
    # only inputs (beyond query/lang/county) that change the answer
    if not rice_fields: return ""
    items = sorted((f.get("field_name",""), f.get("last_flood_date","")) for f in rice_fields)
    return hashlib.sha1(json.dumps(items).encode()).hexdigest()[:12]

def answer_cache_key(en_message, language, county_fips, rice_fields) -> str:
    raw = f"{_normalize(en_message)}|{language}|{county_fips}|{_profile_sig(rice_fields)}"
    return "answer:" + hashlib.sha1(raw.encode()).hexdigest()

def get_cached_answer(key) -> dict | None:   # cache.cache_get(key)
def set_cached_answer(key, advisory: dict, ttl=config.REDIS_TTL_SECONDS) -> None  # cache.cache_set

def is_cacheable_as_reference(advisory: dict) -> bool:   # JS port
```

Backed by the existing `cache.cache_get`/`cache_set` (Upstash, graceful no-op
when Redis is unset). Key is on the **English** message (post-translate) but
**includes `language`**, so the stored advisory is the user-facing one (an ES
hit returns the ES advisory directly — no re-translation).

### `routers/query.py` flow

READ — after sanitize + `maybe_translate_query` (so `en_message` exists), before
classify, only when `session_history` empty:

```python
cache_key = None
if not session_history:
    cache_key = answer_cache_key(en_message, language, county_fips, rice_fields)
    hit = get_cached_answer(cache_key)
    if hit:
        return _stream_advisory(hit, category=hit.get("_category"), session_id=req.session_id, ...)
```

The hit path streams the stored advisory envelope frame + `[DONE]` (same
event-stream content-type, so the frontend path is unchanged) and saves the
user+assistant messages when `session_id` is present. No progress frames (it is
instant). classify/retrieve/generate/guard all skipped.

WRITE — in `event_stream`, after the final advisory is built (post-ES-translate),
only when `cache_key` is set (first-turn), the advisory is not suppressed, and
`is_cacheable_as_reference(result.model_dump())`:

```python
if cache_key and not result.suppressed and is_cacheable_as_reference(payload_advisory):
    set_cached_answer(cache_key, {**payload_advisory, "_category": category})
```

Stored value = the advisory `model_dump()` plus `_category` (so a hit can echo
the category frame). `message_id` is NOT stored — it is per-session and assigned
at save time on the hit.

### Interaction with other levers

- **L1 (progress streaming):** a cache HIT emits no progress stages (instant
  final frame). A MISS runs the normal staged flow and WRITEs at the end.
- **L4:** unaffected (hit skips context entirely).
- Rate limiting stays BEFORE the cache check (`query.py:97`) — a cached answer
  still counts as a query.

## Error handling

- Redis down → `cache_get`/`cache_set` no-op (existing behavior); pipeline runs
  normally. Cache is best-effort, never a hard dependency.
- Corrupt/parse-failed cached blob → treat as miss (try/except around
  reconstruction), regenerate.

## Testing (TDD)

- `answer_cache`: `_normalize` collapses case/whitespace/trailing punctuation so
  "Soybean seeding rate, NE Arkansas?" and "soybean seeding rate NE arkansas"
  yield the same key; different county/language/rice_fields → different key;
  a paraphrase ("how many soybean seeds per acre") → different key (MISS).
- `is_cacheable_as_reference`: parity table mirrored from `offlineTiering.test`
  — informational+clean → true; any products_rates/warnings/time-sensitive term
  or non-informational/suppressed → false.
- `query.py`: first-turn cacheable advisory is written then a repeat returns the
  cached frame WITHOUT calling `run_rag_query` (assert mock not called); a query
  WITH session_history neither reads nor writes; a suppressed/rate-bearing
  advisory is never written; ES hit returns ES advisory without re-translation.

## Files touched

- `backend/services/answer_cache.py` — NEW
- `backend/routers/query.py` — READ before classify, WRITE after final advisory,
  shared `_stream_advisory` helper for the hit path
- `backend/tests/test_answer_cache.py` — NEW; `test_query*` extensions

## Verification

`scripts/latency_probe.py` is per-stage and won't show cache (it calls services
directly); add a hit/miss assertion in the query tests instead. Manual: same
informational query twice → second returns in <100ms; a rate/spray query → never
cached (regenerates each time).
