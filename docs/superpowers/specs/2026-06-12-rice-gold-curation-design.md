# Rice Gold-Label Curation — Design Spec (Phase 1.5, data fix)

**Goal:** Curate the rice gold labels in `eval_set_v2_clean.jsonl` so the rice correctness/faithfulness headline measures the pipeline, not the gold quality. The 2026-06-13 rice diagnosis found rice 18% correctness is *substantially an eval-measurement artifact* (`GOLD_ARTIFACT + EVAL_MISLABEL = 58%` of failures; `TRUE_RETRIEVAL = 0`): rice gold labels are pointed at yearly "br wells" research-volume TOCs/citation-lists that carry no actionable recommendations, so a correct how-to answer cannot score `corr=1.0`. This produces a curated rice gold set drawn from the v3 corpus, by independent topical judgment, with a circularity guard that keeps the resulting headline NIW/arXiv-honest.

**Type:** Eval-only **data** curation. Touches no `backend/`, no `frontend/`, no retrieval pipeline. Pure derivation from existing files. Not a lever — it corrects how rice is *graded*, not how it is *answered*.

**Branch:** new feature branch off `main` (eval-only → push triggers no HF/Vercel deploy). Merge per branch-safety rule after tests + explicit OK.

**Background docs:** `docs/superpowers/2026-06-13-rice-diagnosis-findings.md` (the 19-item bucket audit + the re-point recommendation), `PROGRESS.md` "RAGAS DIAGNOSTIC MATRIX — RESULTS" (ctx_recall 0.16, rice 0.00\* provisional — the metric this curation un-provisions), `memory/project_eval_contamination.md` (the train-on-test trap this spec's circularity guard avoids).

---

## 1. Inputs and outputs

**Inputs (read-only, never mutated):**
- `evals/eval_set_v2_clean.jsonl` — the current canonical eval set, 198 rows (111 rice). Each row: `{query, chunk_id, chunk_text, document_title, namespace}`. Rice gold uses pre-Docling v2 chunk_ids.
- `ingestion/en_chunks/corpus_v3.jsonl` — the v3 Docling corpus, 21,065 chunks (rice 16,392), matching the live `agroar-prod-gte-v3` index. Each chunk: `{chunk_id, document_title, namespace, source_text, retrieval_text, ...}`. This is the source for re-pointed gold so gold text aligns with what the prod index actually retrieves.

**Output (new file, originals preserved):**
- `evals/eval_set_v2_clean_rice.jsonl` — same schema, rice rows curated (some dropped, some re-pointed), soybeans/poultry rows copied through unchanged.
- `docs/superpowers/2026-06-12-rice-gold-curation-audit.md` — the human-reviewable audit table of every change.

`eval_set_v2.jsonl` (pristine original) and `eval_set_v2_clean.jsonl` both stay untouched, preserving provenance.

---

## 2. The curation flow

```
eval_set_v2_clean.jsonl (111 rice rows)
   │
   ├─ 1. FLAG yearly-volume gold  — flag rice rows whose gold document_title
   │        matches the yearly-research-volume pattern (regex over "br wells",
   │        "rice research stud…", a leading 4-digit year). Deterministic,
   │        auditable count. = the GOLD_ARTIFACT population across all 111.
   │
   ├─ 2. DROP wrong-crop items   — remove the corn-nitrogen item (#9) and the
   │        soybean-variety item (#10): neither is a rice question and no
   │        corn/general retrieval namespace exists to relabel into.
   │
   ├─ 3. RE-POINT (flagged rows + the cross-namespace #6) — for each, run an
   │        independent candidate search over corpus_v3 by the QUESTION's topic
   │        terms, pick the agronomically-correct chunk, set new gold =
   │        {its v3 chunk_id, source_text, document_title}.
   │
   ├─ 4. AUDIT — emit one row per change {query, old_gold_title, new_gold_title,
   │        new_chunk_id, action, reason} → markdown for Taiwo spot-check.
   │
   └─ 5. WRITE eval_set_v2_clean_rice.jsonl.
```

### Circularity guard (the honesty crux)

Re-pointed gold must be chosen by **independent topical correctness**, never by what the model retrieved. Two concrete defenses:

1. **Different mechanism.** Candidate search uses a keyword/term match over v3 `source_text`, deliberately *not* the prod gte-dense embedder. The gold is therefore not selected by the same machinery being evaluated.
2. **Blind to the dump.** The re-point decision is made without reading the model's `retrieved_chunks`/`chunk_snippets` from any eval dump. Gold = the correct topical doc by agronomy judgment, never "the doc the model happened to surface."

This is what keeps the post-curation rice headline honest (avoids the train-on-test inflation that invalidated the MRR 0.65 figure — see `project_eval_contamination`). The candidate search only *surfaces* options; a human-checked agronomy judgment *chooses*, and the audit table makes that choice reviewable.

---

## 3. Units (each isolated + unit-testable, $0)

All live in a new `evals/rice_gold_curation.py`; pure helpers, no LLM, no network.

| Unit | Responsibility | Signature (intent) | Test |
|---|---|---|---|
| `flag_yearly_volume_gold(rows)` | identify rice rows whose gold `document_title` is a yearly research-volume TOC | `rows → list[flagged row]` | known yearly-volume titles flagged; topical titles not |
| `candidate_chunks(question, corpus, k=10)` | keyword/term search over v3 `source_text`, independent of gte | `(query, corpus) → ranked candidates` | seeded mini-corpus → expected topical chunk ranks top |
| `apply_curation(rows, decisions)` | apply a decisions table: DROP rows, REPOINT gold fields | `(rows, decisions) → new rows` | drop removes row; repoint swaps chunk_id/text/title; others pass through |
| `write_audit(decisions, rows)` | render the human-review markdown table | `decisions → md string` | every change row present with all fields |

**The decisions table** is the single human-authored artifact: a mapping `query → DROP | REPOINT(new_chunk_id)`. It is populated by running `candidate_chunks` + agronomy judgment (the human-in-the-loop step), then codified as data so `apply_curation` stays pure and testable. Hardcoding edits inside `apply_curation` is explicitly rejected — decisions-as-data keeps the transform deterministic and the audit honest.

---

## 4. Validation (asserted in the build, before the file is accepted)

- **Existence:** every re-pointed `chunk_id` exists in `corpus_v3.jsonl`.
- **Fix actually moved:** every re-pointed gold `document_title` does NOT match the yearly-volume pattern (the re-point left the TOCs).
- **Row math:** `len(curated) == len(clean) − dropped`; soybeans/poultry counts unchanged.
- **Coverage:** the audit table has one row per diff between clean and curated — no silent edits.
- **Schema:** curated rows carry exactly the original 5 keys.

---

## 5. Re-measure (paid — cost-gated, explicit OK each time)

Curation is $0 (pure data + helpers). Measuring its effect spends tokens:

- **Headline re-run:** `answer_eval_full.py --provider deepinfra --judge-provider gemini --eval-set evals/eval_set_v2_clean_rice.jsonl --sample 40 --seed 7` → the new honest rice corr/faith. Compare to the pre-curation rice 18-21%.
- **RAGAS re-run (optional):** `ragas_eval.py` on a fresh capture dump → un-provisions rice `context_recall` (was 0.00\*).

Both behind explicit Taiwo OK, per the cost rule. The build session stops at the $0 curation + validation; re-measure is a separate gated step.

---

## 6. Scope guard (YAGNI)

- **Rice only.** Soybeans and poultry gold copy through untouched.
- **No synthetic gold.** Phase 2 (RAGAS synthetic ground-truth + human-validated subset) is a separate later spec; this curation is the hand-audit it would otherwise absorb, done now because it is $0 and unblocks the trustworthy rice headline.
- **No retrieval work.** `TRUE_RETRIEVAL = 0` in the diagnosis — retrieval surfaced an on-topic doc in every rice failure. The closed-retrieval guardrail stands.
- **No pipeline/prompt changes.** This does not touch `rag.py`, the guard, or `utils/prompt.py`.

---

## 7. Self-review notes

- **Placeholders:** none — every unit has a signature and a test; every input/output path is concrete.
- **Consistency:** the v3-corpus gold source (§1) is what makes both the RAGAS `context_recall` un-provisioning (§5) and the alignment-with-live-index rationale coherent; the circularity guard (§2) is the reason the §5 headline is citable. No section contradicts another.
- **Scope:** single implementation plan — one new module, one new data file, one audit doc, four pure units + a human decisions step + a gated re-measure. Appropriately sized.
- **Ambiguity resolved:** "re-point" is defined as drawing new gold from corpus_v3 by independent keyword search + agronomy pick, blind to the eval dump — not by reusing retrieved chunks.
