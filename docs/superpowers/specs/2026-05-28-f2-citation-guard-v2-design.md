# F2 — Calibrated Uncertainty + Claim-Level Citation Guard

**Date:** 2026-05-28  
**Status:** Approved  
**PRD ref:** §F2  

---

## Overview

Adds NLI-based claim verification to every RAG response. Each answer is decomposed into atomic factual claims, each claim is scored against the retrieved chunks via a cross-encoder, and the mean entailment score becomes `confidence_score`. Low-scoring responses trigger county Extension agent escalation or full suppression.

NIW angle: "first deployment of claim-level NLI entailment guard in US agricultural advisory" — arXiv Prong 1 contribution.

---

## Architecture & Data Flow

```
run_rag_query()
  ├── retrieval + LLM (existing)
  └── _postprocess()
        ├── [existing] title-match citation guard → prune invalid citations
        └── [NEW] citation_guard_v2.verify_answer()
              ├── decompose_claims(answer_text) → Gemini Flash Lite → list[str]
              ├── for each claim: CrossEncoder vs top-3 chunks → {label, score}
              ├── score_answer() → mean ENTAILED score → confidence_score float
              ├── if score < 0.4 → escalation = county_agents[fips]
              └── if score < 0.2 → suppress answer body
        └── stamp confidence_score + claim_verification + escalation onto AdvisoryResponse
```

NLI runs async inside `_postprocess` — latency added after LLM generation, before SSE stream end. ~200–500ms acceptable.

---

## Components

### `backend/services/citation_guard_v2.py` (new)

- `decompose_claims(answer: str) -> list[str]`  
  Single Gemini Flash Lite call, structured output `list[str]`, max 8 claims.  
  Fallback: sentence-split on `.` if Gemini call fails.

- `verify_claim(claim: str, chunks: list[str]) -> ClaimResult`  
  CrossEncoder(`cross-encoder/nli-MiniLM2-L6-H768`) scores claim vs each chunk.  
  Takes max score per chunk across top-3 chunks.  
  Label = argmax of `[CONTRADICTION, NEUTRAL, ENTAILMENT]` logits.

- `score_answer(results: list[ClaimResult]) -> float`  
  Mean of scores where `label == ENTAILED`.  
  Empty claims list → `1.0` (no claims to contradict).

- `escalation_cue(county_fips: str) -> str | None`  
  Loads `backend/data/county_agents.json` once at module level.  
  Returns formatted contact string (`"Contact: {agent_name}, {phone}, {email}"`) or `None` if fips missing.

- `verify_answer(answer: str, chunks: list[dict]) -> dict`  
  Orchestrates above. Returns `{confidence_score, claim_verification, escalation}`.  
  Input `answer` = farmer-facing prose only (`problem_summary` + `recommended_actions` joined), not full JSON.

### `backend/data/county_agents.json` (new)

Schema:
```json
{
  "05001": {
    "county": "Arkansas County",
    "agent_name": "...",
    "phone": "...",
    "email": "..."
  }
}
```
75 AR counties. Built by `ingestion/scrape_county_agents.py`.

### `ingestion/scrape_county_agents.py` (new)

Playwright-based one-shot scraper. Source: `uaex.uada.edu/about/county-extension-offices/`.  
Output: `backend/data/county_agents.json`.  
Run once: `python ingestion/scrape_county_agents.py`.

### `backend/models/advisory.py` (modified)

Add `ClaimResult` model:
```python
class ClaimResult(BaseModel):
    claim: str
    label: Literal['ENTAILED', 'NEUTRAL', 'CONTRADICTED']
    score: float
```

Extend `AdvisoryResponse` (all Optional, all default None — backwards compat):
```python
confidence_score: Optional[float] = None
claim_verification: Optional[list[ClaimResult]] = None
escalation: Optional[str] = None
```

Existing `confidence: Literal["High", "Medium", "Low"]` unchanged.

### `backend/services/rag.py` (modified)

`_postprocess` changes:
1. After existing citation guard, call `citation_guard_v2.verify_answer(answer_prose, chunks)`.
2. Stamp `confidence_score`, `claim_verification`, `escalation` onto result via `model_copy`.
3. If `confidence_score < 0.2`: clear `problem_summary`, `likely_causes`, `recommended_actions`, `products_rates`; set `warnings` to `[escalation_message]`.
4. If `confidence_score < 0.4` and `score >= 0.2`: set `escalation` field only (answer body intact).

### Frontend: `NLIConfidenceBadge.jsx` (new)

Sibling of existing `ConfidenceBadge.jsx`.  
Reads `confidence_score` float:
- `>= 0.7` → green badge
- `0.4–0.69` → amber badge  
- `< 0.4` → red badge

Displays numeric score (e.g., `0.82`). Renders `null` if `confidence_score` absent (backwards compat for old messages).

### `AdvisoryCard.jsx` (modified)

- Render `<NLIConfidenceBadge confidence_score={response.confidence_score} />` alongside existing `<ConfidenceBadge>`.
- If `response.escalation` set: render amber escalation card below `ConfidenceExplainer` with contact string.
- Claim-level detail NOT exposed to farmers. Stored in DB only.

### `backend/migrations/008_confidence_scores.sql` (new)

```sql
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS confidence_score float;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS escalated bool;
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS answer_confidence_mean float;
```

### Eval / nightly CI

Add to nightly eval aggregation:
- `avg(confidence_score)` → `answer_confidence_mean` on `eval_runs`
- `% answers where escalated = true`
- `% CONTRADICTED claims` across all `claim_verification` rows

---

## Thresholds

| Score | Action |
|---|---|
| `>= 0.7` | Green badge, no escalation |
| `0.4–0.69` | Amber badge, escalation card shown |
| `0.2–0.39` | Red badge, escalation card shown |
| `< 0.2` | Answer body suppressed, escalation only |

Thresholds tunable during eval — not hardcoded, defined as constants in `citation_guard_v2.py`.

---

## New Files Summary

| File | Purpose |
|---|---|
| `backend/services/citation_guard_v2.py` | NLI engine |
| `backend/data/county_agents.json` | 75 AR county agent contacts |
| `ingestion/scrape_county_agents.py` | One-shot scraper |
| `backend/migrations/008_confidence_scores.sql` | DB migration |
| `frontend/src/components/advisory/NLIConfidenceBadge.jsx` | Float score badge |

## Modified Files Summary

| File | Change |
|---|---|
| `backend/models/advisory.py` | Add `ClaimResult`, 3 Optional fields on `AdvisoryResponse` |
| `backend/services/rag.py` | `_postprocess` calls `verify_answer`, stamps fields, applies thresholds |
| `frontend/src/components/advisory/AdvisoryCard.jsx` | Add `NLIConfidenceBadge` + escalation card |

---

## Success Metrics (PRD)

| Metric | Target |
|---|---|
| `answer_confidence_mean` | > 0.75 |
| `% answers escalated` | < 15% |
