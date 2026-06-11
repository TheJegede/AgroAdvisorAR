# Citation Guard & RAG Groundedness — Remediation Plan

**Date:** 2026-05-29
**Owner:** Taiwo Jegede
**Source:** `/code-review` full diagnosis (this session). Triggered by observed
answer suppression across crops; root cause is the citation-guard groundedness
design, not a single threshold.

## STATUS (updated 2026-05-29, after the Spanish translate-bridge reframe)

- ✅ **P0** (contradiction override + empty-chunks ungrounded) — DONE (`fc382e3`).
- ✅ **P1.1** (fall back only on quota, re-raise real errors) — DONE (`e4c06ad`).
- ✅ **P1.2** (per-namespace harness) — DONE (`0a8ed04`).
- ✅ **P2.1** (paraphrase/number-tolerant groundedness) — DONE (`a6a2d57`).
- ✅ **gte+reranker EN retrieval** (was "out of scope") — DONE this session
  (`agroar-prod-gte`); cut suppression 80%→0% on the EN path.
- ❌ **P2.2 (language-aware guard) — OBSOLETE.** The Spanish translate-bridge
  (`docs/.../2026-05-29-spanish-translate-bridge-design.md`) translates ES→EN
  *before* the pipeline, so the guard only ever sees English. `detected_lang`
  was removed. No multilingual NLI needed — skip this entirely.
- ⏳ **P2.3** (calibrate thresholds per namespace) — PENDING; now simpler (one
  English distribution; ES rides the same English guard).
- ⏳ **P3.1** (single provider abstraction) — PENDING; scope grew to **4** files
  (`rag.py`, `classifier.py`, `citation_guard_v2.py`, **`translation.py`**).
- ⏳ **P3.2** (harden local adapter) — PENDING.

**Remaining work = P2.3 + P3.1 + P3.2 (all polish; none blocks deploy/pilot).**
Phases below are the original plan; treat P0/P1/P2.1 as historical record.

## Problem summary

The NLI citation guard (`backend/services/citation_guard_v2.py`) decides whether
a farmer sees an advisory or a "contact Extension" referral. The review found it
is unsound on five axes:

- **Wrong tool:** per-claim *hard NLI entailment* penalizes correct paraphrase
  and any specific number/product/rate not stated verbatim — exactly the
  high-value advice (e.g. rice "150 lb N/ac" scored 0.118 → suppressed).
- **Not language-aware:** `nli-MiniLM2-L6-H768` is English-only but ES answers
  (F1 multilingual path) run through it → ES disproportionately suppressed.
- **Not crop-aware:** `chunks[:3]` + one global threshold over non-uniform
  corpora (poultry smaller/chunked differently than rice/soybean) → uneven
  suppression; nothing measures `confidence_score` per namespace.
- **Uncalibrated thresholds:** `SUPPRESSION_THRESHOLD=0.2` / `ESCALATION=0.4`
  are guesses ("tune during eval"); the recent `score_answer` change moved the
  operating point with no recalibration.
- **Under-suppression holes introduced this session:** averaging entailment over
  all claims dilutes a CONTRADICTED claim; empty/missing chunks score 0.5 and
  pass. Plus silent-failure regressions in the provider/classifier paths.

**Verification approach (free, repeatable):** all phases verified with the local
eval — `python evals/answer_eval_full.py --provider local` (Qwen-7B on GPU, zero
quota) and direct `run_rag_query` calls. Where per-crop numbers are needed, the
P1 measurement harness segments by namespace.

---

## Phase 0 — CRITICAL: close the safety under-suppression holes

A wrong chemical rate reaching a farmer is the worst failure mode. These are
small, surgical, ship first.

### 0.1 Suppress on any contradicted claim (stop dilution)
- **File:** `citation_guard_v2.py` (`score_answer`, and the suppression decision).
- **Change:** keep mean entailment probability as the *groundedness* score, but
  add a hard rule: if **any** claim is labeled `CONTRADICTED` (entailment prob
  below a small floor, e.g. `< 0.15`), force suppression/escalation regardless
  of the mean. A contradiction must never be diluted by neutral claims.
- **Accept:** unit test — claims `[ENTAILED 0.9, NEUTRAL 0.6, CONTRADICTED 0.05]`
  → guard suppresses (today it serves at mean 0.52).

### 0.2 Empty/insufficient chunks must not score as grounded
- **File:** `citation_guard_v2.py` (`verify_claim` empty-chunks branch +
  `verify_answer`).
- **Change:** when there are no usable chunks (or fewer than N), groundedness
  must be **low (→ suppress)**, not the current 0.5 NEUTRAL default that now
  passes the 0.2 gate. Distinguish "no evidence" from "neutral evidence."
- **Accept:** `run_rag_query` on a query whose retrieval returns empty snippets
  → suppressed, not shown at confidence 0.5.

### 0.3 Tests
- Update/extend `backend/tests/test_citation_guard_v2.py` for 0.1 and 0.2.

---

## Phase 1 — HIGH: restore loud failures + per-crop visibility

### 1.1 Provider fallback only on quota, re-raise real errors
- **Files:** `rag.py` (generation loop), `classifier.py`, `citation_guard_v2.py`
  (`decompose_claims`).
- **Change:** fall back to the next provider only on `RESOURCE_EXHAUSTED`/429/
  rate-limit; **re-raise** other exceptions (auth, schema, bug) so they surface
  instead of silently degrading to wrong-namespace routing / masked bugs /
  tripled latency.
- **Accept:** a non-429 error in the primary provider raises (not silently
  routed to `IN_SCOPE_GENERAL_AG` / "all providers failed").

### 1.2 Per-namespace measurement harness (prerequisite for calibration)
- **File:** extend `evals/answer_eval_full.py` (or a small new reporter).
- **Change:** segment suppression rate, correctness, faithfulness, and mean
  `confidence_score` **by namespace** (rice / soybeans / poultry / es). Run on
  the held-out set with local gen.
- **Accept:** a table showing per-crop suppression + score distribution. This is
  what proves/quantifies the crop skew and feeds P2 threshold calibration.

---

## Phase 2 — MEDIUM: fix the groundedness model (the core design issue)

### 2.1 Replace hard-NLI scoring with paraphrase-tolerant groundedness
- **File:** `citation_guard_v2.py` (`verify_claim`, `score_answer`).
- **Change:** score support with a measure that credits paraphrase + specific
  numbers: blend entailment *probability* with embedding/lexical overlap against
  the chunk, or use an attribution-style scorer. Keep the separate hard
  contradiction check from 0.1.
- **Accept:** rice "apply 150 lb N/ac per N-STaR" (grounded but not verbatim)
  scores above suppression; a fabricated rate still scores low. Per-crop harness
  shows suppression drops on grounded answers without passing ungrounded ones.

### 2.2 Language-aware guard — ❌ OBSOLETE (do not implement)
Superseded by the Spanish translate-bridge: ES queries are translated to English
before retrieval/generation, and the advisory is translated back to Spanish only
*after* the guard runs. The NLI guard therefore only ever scores English text —
there is nothing Spanish for it to mis-score. `detected_lang` was removed from
`rag.py`. No multilingual NLI model is needed.

### 2.3 Calibrate thresholds per namespace from data
- **Files:** thresholds → config; calibration documented in the plan/eval.
- **Change:** set suppression/escalation thresholds from the P1.2 per-crop score
  distributions (e.g. target a defensible suppression rate at a measured
  correctness floor), not arbitrary constants. Make them env-overridable.
- **Accept:** thresholds traceable to eval numbers; per-crop suppression within
  an agreed band.

---

## Phase 3 — LOW: structural cleanup

### 3.1 Single provider-selection abstraction
- **New:** `backend/services/llm_provider.py` — one helper returning the ordered
  provider list (incl. `LLM_PRIMARY=local`), used by **`rag.py`, `classifier.py`,
  `citation_guard_v2.py`, and `translation.py`** (the bridge added a 4th copy of
  the ordering logic, already drifting on which Groq model each uses). Removes the
  duplicated logic.
- **Accept:** the four call sites import one helper; no duplicated ordering.

### 3.2 Harden local-mode adapter (dev-only)
- **File:** `backend/services/local_llm.py`.
- **Change:** defensively coerce `likely_causes` items (default missing
  `explanation`) so a malformed local-model JSON degrades instead of raising
  `ValidationError` with no fallback; treat fully-empty JSON as a generation
  failure, not a confidence-1.0 empty advisory.

---

## Sequencing

P0 → P1 → P2 → P3, one phase at a time, each verified with the local eval before
moving on. P0 and P1.1 are safety/visibility and should land first. P1.2
(per-crop harness) gates P2.3 calibration. P2 is the substantive redesign.

## Out of scope (separate tracks)
- ~~Shipping gte-base + reranker to the EN index~~ — ✅ DONE this session
  (`agroar-prod-gte`); was the dominant lever (suppression 80%→0% on the EN path).
- ~~ES corpus quality (MT-bootstrap)~~ — moot; the dedicated ES corpus/index was
  removed and replaced by the translate-bridge.
- Re-baselining the retrieval benchmark off the contaminated `eval_set_v2`.
- Answer *correctness* (~40%): generation/chunking quality, separate from the guard.
