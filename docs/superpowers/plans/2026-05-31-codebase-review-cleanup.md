# Codebase Review Cleanup — 2026-05-31

**Source:** `/review-code` full-pass (3 parallel Explore agents)  
**Stack:** Python/FastAPI backend + React 19/Vite frontend  
**Files reviewed:** 27 backend · 10 frontend core  
**Verification:** `cd backend && pytest tests/ -q` · `cd frontend && npm run lint && npm run test`

---

## Phase 1 — Delete & Deduplicate
> **Can run in parallel across backend and frontend.**

### Module 1A — Backend: extract shared LLM utils `[PARALLEL]`
**Files:** `backend/services/rag.py`, `backend/services/classifier.py`, `backend/services/citation_guard_v2.py`, `backend/services/translation.py`  
**Action:** Create `backend/utils/llm.py` with:
- `_is_quota_error(e)` — currently copy-pasted in `rag.py:44-52` AND `classifier.py:10-17`
- `_get_groq()`, `_get_gemini()`, `_providers()` — provider chain lazy-init duplicated 3× across rag.py, citation_guard_v2.py, translation.py

Remove all duplicate copies; import from `utils/llm.py`.

### Module 1B — Backend: extract DB assertion helper `[PARALLEL]`
**Files:** `backend/services/session.py:12-14,55-56`, `backend/services/user.py:36-38`  
**Action:** Create `backend/utils/db.py` with `_assert_insert(result, label)`.  
Replace 3 identical `if not result.data: raise RuntimeError(...)` blocks.

### Module 1C — Backend: remove dead code `[PARALLEL]`
**Files:** `backend/services/context.py:3`, `backend/utils/prompt.py:29`  
**Action:**
- Remove unused `import json` from `context.py`
- Remove unused `OUTPUT_INSTRUCTIONS` constant from `prompt.py`

### Module 1D — Frontend: remove inline duplication `[PARALLEL]`
**Files:** `frontend/src/components/advisory/AdvisoryCard.jsx:40-78`  
**Action:**
- Replace `DetailedExplanation` (lines 52-61) and `KeyPoints` (lines 63-78) — identical structure — with single `DetailSection` component
- Inline `CropChip` (10 lines, used once)

---

## Phase 2 — Rename
> **Sequential within backend/frontend; backend and frontend can run in parallel.**

### Module 2A — Backend renames `[PARALLEL with 2B]`
**Files:** `backend/services/citation_guard_v2.py`, `backend/services/translation.py`, `backend/routers/query.py`, `backend/routers/auth.py`  
**Actions:**
- `citation_guard_v2._lexical_support()`: `ct` → `claim_tokens`, `best` → `best_overlap`, `ch` → `chunk`, `cht` → `chunk_tokens`
- `translation._call()` → `_call_llm()`
- `query.py:89`: `oos_message_id` → `out_of_scope_message_id`
- Define named constants:
  - `citation_guard_v2.py`: `CHUNK_PREVIEW_LENGTH = 800` (replaces `ch[:800]`)
  - `context.py`: `FEET_TO_METERS = 0.3048` (replaces magic `0.3048`)
  - `auth.py`: `LOGIN_RATE_WINDOW = 900` (repeated 3× at line 101)
  - `config.py`: `DEFAULT_COUNTY_FIPS = "05055"` (replaces inline default in query.py:79)

### Module 2B — Frontend renames `[PARALLEL with 2A]`
**Files:** `frontend/src/utils/deriveFollowUps.js`, `frontend/src/hooks/useSessions.js`  
**Actions:**
- `deriveFollowUps.js:8`: `arr` → `array`
- `useSessions.js:46`: `getParsedAdvisory(m)` param `m` → `message`

---

## Phase 3 — Simplify
> **Sequential within backend/frontend; backend and frontend can run in parallel.**

### Module 3A — Backend simplifications `[PARALLEL with 3B]`
**Files:** `backend/utils/prompt.py`, `backend/services/translation.py`, `backend/routers/auth.py`, `backend/models/advisory.py`, `backend/config.py`  

1. `prompt.py:37-46`: Merge `OUT_OF_SCOPE_MESSAGE` + `OUT_OF_SCOPE_MESSAGE_ES` into `OUT_OF_SCOPE_MESSAGES = {"en": ..., "es": ...}`; update all callers
2. `translation.py:65-66`: `if not text or not text.strip()` → `if not (text and text.strip())`
3. `auth.py:86`: Replace direct `create_client()` call with `_get_anon_client()` — fixes connection-per-request bug
4. `config.py:51`: Move personal email in `NOAA_USER_AGENT` to env var `NOAA_CONTACT_EMAIL`
5. `advisory.py:14,20`: Standardize `Optional[str]` → `str | None` throughout
6. `advisory.py:29-32`: Add `Field(ge=0, le=1)` to `ClaimResult.score`

### Module 3B — Frontend simplifications `[PARALLEL with 3A]`
**Files:** `frontend/src/hooks/useSessions.js`, `frontend/src/pages/ChatPage.jsx`  

1. `useSessions.js:28-75`: Convert 4 nested `async function` declarations inside `useCallback` → arrow functions
2. `ChatPage.jsx:86-96,104-114`: Extract `makeMessage(role, type, content)` factory — duplicate envelope construction
3. `ChatPage.jsx:117`: Move `isTechnical` regex to module-level constant
4. `ChatPage.jsx:89`: Remove `Date.now() + 1` cargo-cult offset — use `Date.now()` or `crypto.randomUUID()`

---

## Phase 4 — Structural (must be sequential, higher risk)
> **Backend and frontend can still run in parallel within this phase.**

### Module 4A — Backend: context.py cache + chaining `[PARALLEL with 4B]`
**File:** `backend/services/context.py`  

1. Extract repeated cache-check-return into helper:
   ```python
   async def _cached_fetch(cache_key: str, fetch_fn, ttl: int):
       cached = cache_get(cache_key)
       if cached:
           return cached
       result = await fetch_fn()
       if result:
           cache_set(cache_key, result, ttl=ttl)
       return result
   ```
   Replace 3 occurrences in `fetch_ssurgo`, `fetch_noaa`, `fetch_usgs_well`.

2. Lines 196,200,203,234: Replace defensive chaining `(ts.get("x") or {}).get("y") or {}` with helper or explicit `if ts:` guard blocks

### Module 4B — Frontend: Sidebar bug + useEffect deps `[PARALLEL with 4A]`
**Files:** `frontend/src/components/layout/Sidebar.jsx`, `frontend/src/pages/ChatPage.jsx`  

1. **Bug fix — `Sidebar.jsx:55`**: Audit `handleDeleteSession` — `currentSessionId` in closure may be stale at delete time. Fix by passing `sessionId` directly or using `useRef`.
2. **ChatPage.jsx:37**: Remove `eslint-disable-line react-hooks/exhaustive-deps`; fix actual deps or justify suppression with a comment
3. **ChatPage.jsx:58**: Same — audit `loadSession`/`sessionParam` deps
4. **Sidebar.jsx refactor**: Split 235-line component:
   - `SessionsList` (lines 121-158)
   - `SidebarFooter` (lines 220-230)
   - Keep `SidebarNavItem` as-is (already extracted)

---

## Phase 5 — Verify
> **Run after all phases complete.**

```bash
# Backend
cd backend && python -m pytest tests/ -q

# Frontend
cd frontend && npm run lint && npm run test
```

**Known pre-existing failing test** (do not fix here):  
`backend/tests/test_citation_guard_v2.py::test_verifiable_text_includes_all_advisory_fields`

---

## Issue Register (full list)

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | Critical | `Sidebar.jsx:55` | Stale `currentSessionId` in delete handler closure |
| 2 | Critical | `ChatPage.jsx:37,58` | `useEffect` deps suppressed with eslint-disable |
| 3 | Critical | `auth.py:86` | `create_client()` bypass of singleton |
| 4 | High | `rag.py:44` + `classifier.py:10` | `_is_quota_error()` duplicated |
| 5 | High | `rag.py`, `citation_guard_v2.py`, `translation.py` | Provider chain init duplicated 3× |
| 6 | High | `translation.py:121-142` | Fragile manual index arithmetic for advisory remap |
| 7 | High | `config.py:51` | Personal email hardcoded in prod config |
| 8 | High | `context.py:3` | Unused `import json` |
| 9 | High | `prompt.py:29` | Dead `OUTPUT_INSTRUCTIONS` constant |
| 10 | Med | `rag.py:171-291` | `_postprocess_async()` 120 lines, 3+ responsibilities |
| 11 | Med | `rag.py:294-428` | `run_rag_query()` 134 lines |
| 12 | Med | `citation_guard_v2.py:219-266` | `verify_claim()` 47 lines, 3 responsibilities |
| 13 | Med | `citation_guard_v2.py:149-157` | Cryptic abbrevs `ct/ch/cht/best` |
| 14 | Med | `citation_guard_v2.py:189` | `ch[:800]` magic number |
| 15 | Med | `context.py:196,200,203,234` | Excessive defensive chaining |
| 16 | Med | `context.py:42-46,86-89,159-162` | Cache-check-return duplicated 3× |
| 17 | Med | `context.py:212` | `0.3048` magic number |
| 18 | Med | `query.py:79` | Hardcoded default county FIPS `"05055"` |
| 19 | Med | `auth.py:101` | Rate window `900` repeated 3× |
| 20 | Med | `translation.py:49` | `_call()` too generic |
| 21 | Med | `prompt.py:37-46` | Separate EN/ES OOS message constants |
| 22 | Med | `session.py`, `user.py` | `if not result.data` pattern duplicated 3× |
| 23 | Med | 8+ files | Bare `except Exception:` swallowing real errors |
| 24 | Med | `AdvisoryCard.jsx:52-78` | `DetailedExplanation`/`KeyPoints` identical structure |
| 25 | Med | `Sidebar.jsx` | 235 lines — needs split |
| 26 | Med | `ChatPage.jsx:86-96,104-114` | Duplicate message envelope construction |
| 27 | Med | `ChatPage.jsx:89` | `Date.now() + 1` cargo-cult |
| 28 | Med | `ChatPage.jsx:117` | Inline `isTechnical` regex |
| 29 | Low | `advisory.py:14,20` | Mixed `Optional[str]` / `str \| None` |
| 30 | Low | `advisory.py:29-32` | `score: float` has no range constraint |
| 31 | Low | `context.py:6` | Non-standard `_date` alias |
| 32 | Low | `prompt.py` | Missing `-> str` return type |
| 33 | Low | `MessageBubble.jsx:3-4` | ID used as timestamp — fragile |
| 34 | Low | `useSessions.js:28-75` | Nested `async function` in `useCallback` |
| 35 | Low | `deriveFollowUps.js:8` | `arr` param name |

---

## Out of scope (not reviewed)
- `backend/services/drift_service.py`, `pdf_generator.py`, `alert_engine.py`
- `backend/routers/admin.py`, `alerts.py`, `feedback.py`
- `evals/`, `ingestion/`
- Migration SQL (append-only)
