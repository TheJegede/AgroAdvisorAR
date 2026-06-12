# Code Review Findings — 2026-06-12 (deferred fixes)

Full-codebase review of everything shipped since the 2026-06-05 logic review
(`ea14686..HEAD`, ~5,300 production lines across 88 files). Graphify-guided,
inline verification (no subagents). All findings verified against actual code —
file:line quoted. Status: **8 of 10 FIXED 2026-06-12 (TDD, backend 285 green)** —
F1,F2,F3,F4,F6,F7,F8,F10 done + pushed; **F5 CLOSED** (batched-eval probe clean,
0 fake-citation bleed / 40 answers), **F9 DEFERRED** (latent). See PROGRESS.md
"CODE-REVIEW REMEDIATION 2026-06-12" + "L2 FEW-SHOT EXEMPLARS = MEASURED WIN".

Clean areas (verified, do NOT re-review): spray_record/feedback anti-IDOR,
auth refresh single-flight + `_retry` guard, SSE heartbeat loop (race-free,
cancel-safe), L3 answer-cache eligibility gates, station math
(haversine/bearing/angular_diff), chunker/embed_corpus (Docling v3).

---

## P0 — fix before pilot

### 1. Timezone mismatch: UTC `at` vs Open-Meteo America/Chicago local times
- **Files:** `backend/services/weather_now.py:117` (`_naive(at)` strips tzinfo),
  `:43` (`_estimate_inversion` comparisons), `backend/services/spray_check.py:46`
  (`req.at.date()`), `backend/routers/dicamba.py:37` (`resolve_rules(body.at.date())`)
- **Root cause:** frontend sends `new Date().toISOString()` (UTC "Z",
  `useSprayCheck.js:9`); pydantic parses tz-aware; backend strips tzinfo and
  compares the UTC *clock* against Open-Meteo timestamps returned in
  `timezone=America/Chicago` local time.
- **Symptoms (one root cause, three safety-relevant effects):**
  1. Inversion estimate: 6:30am CDT check → `at_naive` = 11:30 → "away from
     dawn/dusk" → risk "low" at literal dawn.
  2. Precip window `[at, at+48h)` shifted ~5h forward → rain forecast in the
     next ~5 local hours excluded from `rain_free_48h` → false pass.
  3. Gate A / rules resolution uses the UTC date → June 30 8pm CDT evaluates
     as July 1 → wrong season-window verdict at the cutoff boundary.
- **Fix:** convert `at` to `America/Chicago` via `zoneinfo.ZoneInfo` at the
  router boundary (or inside `weather_now` + `spray_check`) before any
  naive-local comparison or `.date()` call. One small patch covers all three.

### 2. Zero-coverage precip window returns 0.0 → false Gate C pass
- **File:** `backend/services/weather_now.py:121-133`, returned at `:150`
- **Bug:** `precip_sum` starts 0.0; if zero forecast hours match `[at, at+48h)`
  (API allows any future `at`; only the wizard pins `at`=now), the value is
  still `0.0`, not `None` → `rain_free_48h` passes with no data.
- **Fix:** count matched hours; 0 matches → return `None` for
  `precip_next_48h_in` → check degrades to `needs_confirmation` (existing
  `value is None` branch in `spray_check.verifiable()` already handles it).

### 3. DB-trusted history injects raw advisory JSON blobs into the prompt
- **File:** `backend/routers/query.py:53` (`_normalize_history`), source rows
  from `services/session.get_messages`
- **Bug:** assistant rows with `content_type='advisory'` store
  `json.dumps(full AdvisoryResponse)` (~2KB each, citations/context_meta
  included). `_normalize_history` filters only on `role`, never
  `content_type` → up to 10 raw JSON blobs land verbatim in
  `[CONVERSATION HISTORY]` (`utils/prompt.py:213-219`) on every follow-up →
  ~20KB prompt bloat (Groq TPM pressure, latency) + JSON-structured assistant
  turns conditioning the model.
- **Fix:** in `_normalize_history`, for advisory rows parse the JSON and keep
  only `problem_summary` (fallback: skip row); keep `content_type='text'` rows
  as-is. `get_messages` already returns `content_type`.

---

## P1 — guard / answer-quality

### 4. Merged judge returning `[]` → confidence 1.0 guard bypass
- **File:** `backend/services/citation_guard_v2.py:455` (`if not results:`
  branch in `verify_answer`), `judge_answer_llm` returns `[]` when judge emits
  empty array
- **Bug:** lazy/refusing judge returns `[]` for a substantive answer → treated
  as "no claims to verify" → confidence 1.0, suppression impossible. Old
  two-step path had sentence-split fallback guaranteeing claims for non-empty
  answers — this is a regression vs that.
- **Fix:** in `judge_answer_llm`, treat empty claim list for a non-trivial
  answer (e.g. `len(answer.strip()) > 80`) as a provider failure → raise →
  caller falls back to decompose+judge two-step.

### 5. Few-shot exemplar fabricated-citation bleed
- **File:** `backend/utils/prompt.py:62` (`FEW_SHOT_EXEMPLARS`), appended
  unconditionally at `build_system_prompt` tail
- **Risk:** exemplars embed realistic fake citations ("Arkansas Herbicide
  Guide 2026", "Arkansas Insect Management Handbook 2026", county_fips 05031).
  Model copies exemplar citation into a real answer → v3 index carries titles
  → title-match guard finds no retrieved doc with that title → confidence
  forced Low → suppression of otherwise-grounded answers. Also +~1.2k tokens
  on EVERY query (follow-ups + SAFETY_CRITICAL included).
- **Action:** do NOT fix blind — this is exactly what the pending batched
  DeepInfra eval (v3 corpus + L2 effect) measures. During that eval, grep
  outputs for the exemplar titles/fips as a contamination probe. If bleed
  confirmed: rename exemplar citations to obviously-synthetic
  ("EXAMPLE-DOC-A"), and consider gating exemplars off for follow-up turns to
  cut token cost.

### 6. Judge-array claim/label misalignment on non-dict entries
- **File:** `backend/services/citation_guard_v2.py:~270` (`judge_answer_llm`
  claims extraction) + `_postprocess_judge_array` zip
- **Bug:** `claims` list-comp drops non-dict entries but post-processing zips
  against `parsed[:8]` *including* them → claim i pairs with wrong object →
  wrong label/score; `len(out)==len(claims)` still passes so no fallback fires.
- **Fix:** filter `parsed` to dicts ONCE, use that same list for both claim
  extraction and post-processing.

---

## P2 — polish / latent

### 7. O(n²) partial-frame SSE payload
- **Files:** `backend/services/rag.py:33` (`_astream_draft`), `_on_partial_cb`
  ~`:525`; frontend `useSSEQuery` `setProvisional` per frame
- **Cost:** every JsonOutputParser update re-sends the full cumulative draft
  dict → hundreds of KB per query through the Vercel→HF proxy + a React
  re-render per frame.
- **Fix:** throttle `_on_partial_cb` (emit at most every ~250ms), or emit only
  when a top-level field completes.

### 8. Naive `datetime.now()` in immutable spray record
- **File:** `backend/services/spray_check.py:453` (`evaluated_at`)
- **Bug:** HF container runs UTC; frozen legal record shows
  `2026-06-12T23:30:00` with no offset → ambiguous vs farmer's CDT spray time
  in a drift dispute.
- **Fix:** `datetime.now(timezone.utc)`.

### 9. Rain-check label vs hardcoded 48h data window (latent)
- **File:** `backend/services/spray_check.py:268`
- **Bug:** label interpolates `rain_free_hours_required` from rules-as-data,
  but the value checked is always `precip_next_48h_in`. Rules currently say 48
  → consistent today. A future rules record with 24 would display "within 24
  hours" while still evaluating 48h; >48 would silently under-check.
- **Fix:** make `weather_now` accept the hours value (plumb
  `rain_free_hours_required` through `fetch_forecast_conditions`), or assert
  `rain_hours == 48` at load time so divergence fails loudly.

### 10. sanitize() hard-400s the whole query on bad client history
- **File:** `backend/routers/query.py:131` (`_trusted_rag_history` →
  `_normalize_history(sanitize_content=True)`)
- **Bug:** legacy no-session_id flow: a prior advisory in client
  `session_history` containing a sanitizer trigger phrase or exceeding max
  length → `InjectionDetected`/`MessageTooLong` → entire NEW query rejected
  400.
- **Fix:** catch per-row inside `_normalize_history` and drop the offending
  row instead of propagating.

---

## Housekeeping (not findings)
- `.gitignore`: add `ingestion/stderr.txt`, `ingestion/backup_pdfs/`
- Decide: commit or delete `ingestion/spot_check.py`; commit modified
  `docs/superpowers/plans/2026-06-12-docling-v3-cutover.md`

## Suggested implementation order
1+2 together (one `weather_now.py`/`spray_check.py` patch + tz conversion at
router), then 3 (two-line filter + tests), then 8 (one-liner, same files as
1), then 4+6 (guard, same file), then 10, then 7. Hold 5 for the batched eval.
TDD per CLAUDE.md conventions; backend suite currently 236 green — keep it.
