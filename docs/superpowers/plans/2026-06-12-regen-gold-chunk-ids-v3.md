# PARKED FOLLOW-UP — Regenerate eval-set gold chunk_ids against v3

> **Status: PARKED. Do not build until passage-level retrieval eval (MRR / recall@k)
> is actually needed.** The corpus-gap split (2026-06-12) used document-title hit@5 and
> did NOT need this. Decision already made (next lever = L3 generation). This plan exists
> so the repair is ready when passage-level numbers are wanted again.

**Why this exists:** `evals/eval_set_v2.jsonl` stores gold `chunk_id`s minted against the
v2 index. The Docling v3 re-ingest (968bc42) re-chunked every document → new chunk_ids →
**zero** eval gold ids exist in `agroar-prod-gte-v3` (verified by `index.fetch`). So any
exact-chunk retrieval metric (MRR, recall@k, exact hit@5) is impossible on v3 until the
gold ids are re-pointed to their v3 equivalents.

**Why it is NOT a clean lookup:** v3 re-chunked with different boundaries. The gold answer-
key stores a v2 chunk *text* (≈512-char slice); no v3 chunk is byte-identical to it. The
same content is now split differently. So each gold must be **matched** to its closest v3
chunk, not looked up.

**Cost:** zero LLM (local gte-base embed + Pinecone reads only). One engineering session.
Optional paid LLM judge ONLY for the ambiguous tail (cost-gated, get OK first).

---

## Approach: embed-match each gold chunk_text → best v3 chunk, with a confidence gate

### Task 1: Build the re-pointer (TDD pure helpers)
- Create `evals/regen_gold_ids.py` with pure, offline-testable helpers:
  - `best_match(gold_vec, cand_vecs) -> (idx, score)` — argmax cosine.
  - `decide(score, hi=0.92, lo=0.85) -> "auto" | "review" | "miss"` — banded confidence.
- Create `evals/test_regen_gold_ids.py` — offline tests for both (mocked vectors).
- Rationale for bands: same-crop agronomy floors ~0.83 cosine (measured in the corpus-gap
  session), so a plain threshold is unreliable. Use a HIGH bar (≥0.92) for auto-accept,
  a middle band (0.85–0.92) flagged for human review, and `<0.85` = the gold doc/passage
  may have been dropped or heavily re-segmented in v3 → record as a real corpus change.

### Task 2: Run the match (zero LLM cost)
- For each item: embed gold `chunk_text` (gte-base), retrieve / scan candidate v3 chunks
  **within the same `document_title`** (stable key — narrows the search and prevents
  cross-document mis-matches), cosine vs each, take `best_match` → `decide`.
- Write `evals/_gold_id_remap.jsonl`: `{query, old_id, new_id, score, band, document_title}`.
- Print band counts (auto / review / miss).

### Task 3: Human review of the middle band + misses
- Print every `review`/`miss` item: gold text snippet vs the candidate v3 chunk text, side
  by side. Accept / correct / mark-dropped by hand. (This is the irreducible manual step —
  boundary changes mean some golds legitimately split across 2 v3 chunks; pick the one that
  contains the answer rate/fact.)
- Record decisions in `docs/superpowers/<date>-gold-id-regen.md`.

### Task 4: Emit `eval_set_v3.jsonl` (NEVER mutate v2 set)
- Apply auto + reviewed ids; for `miss` items either drop (document gone) or keep with a
  `gold_chunk_id=null` + a `note` so retrieval metrics can exclude them honestly.
- New file `evals/eval_set_v3.jsonl` carries v3 ids + the audited namespaces from
  `eval_set_v2_clean.jsonl` (fold the two cleanups together).

### Task 5: Validate + record
- Sanity: every non-null new id must `index.fetch` successfully on v3.
- Re-run `evals/retrieval_precision.py` with EXACT chunk-id hit@5 (now valid) and compare
  to the document-title hit@5 from the corpus-gap split — they should broadly agree;
  divergence flags bad matches.
- Update `PROGRESS.md`.

---

## Notes for the executor
- **Stable key across the migration = `document_title`.** Always constrain candidate search
  to the same title; never match a gold across documents.
- **Dense cosine is noisy** for same-crop text (~0.83 floor) — that's why the banded gate +
  human review exist instead of a single threshold. Do not lower the auto bar to skip review.
- **Folds in `eval_set_v2_clean.jsonl`** (the 1 relabel + 2 drops from the corpus-gap audit)
  so v3 set is clean labels + v3 ids in one artifact.
- Only spend LLM tokens if you choose an LLM containment judge for the review band — gate it.
