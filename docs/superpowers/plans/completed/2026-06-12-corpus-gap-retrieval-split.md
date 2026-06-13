# Corpus-Gap Retrieval/Generation Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose *why* answer correctness is low (esp. soybeans 14%) by splitting every failing item into one of four causes — RETRIEVAL_MISS / GEN_SPECIFICITY / GEN_HALLUCINATION / LABEL_SUSPECT — using zero-LLM-cost retrieval checks plus an eval-set label audit, so the next engineering lever (corpus vs retrieval vs generation) is chosen on evidence rather than guesswork.

**Architecture:** A small standalone script `evals/retrieval_precision.py` reproduces the *exact* seed=7 sample that produced the L2 dumps, runs retrieval-only (local gte-base embed + Pinecone top-5, NO generation, NO judge), and joins the gold `chunk_id` hit/rank against the already-computed correctness/faithfulness scores in `evals/_out_v3_L2on.jsonl`. A pure decision function maps `(corr, faith, hit@5)` → a failure label. A second task is a human-in-the-loop eval-set label audit producing a cleaned `eval_set_v2_clean.jsonl`. No paid LLM calls in the core plan; the single optional paid re-run is explicitly cost-gated.

**Tech Stack:** Python 3, `sentence-transformers` (gte-base, local), `pinecone`, existing `evals/answer_eval.py` helpers (`sample_items`, `_NS_TO_CAT`), pytest.

---

## Background (read before starting — context the executor lacks)

- **What's already measured (do NOT re-run to re-measure):** paired DeepInfra eval n=20 seed=7 on `agroar-prod-gte-v3`. Per-crop correctness L2-on: poultry 38%, rice 39%, soybeans 14%. **Suppression is 0% across all crops** — the guard-over-suppression problem is solved; do not chase it. The whole remaining gap is correctness.
- **The two dumps already on disk** (per-item, n=20 each): `evals/_out_v3_L2on.jsonl` (with L2 exemplars) and `evals/_out_v3_L2off.jsonl` (baseline). Each record has keys: `namespace, lang, query, suppressed, correctness, faithfulness, confidence_score, corr_rationale, faith_rationale, citations`. **They do NOT contain `chunk_id` or retrieved-chunk text** — that's the gap this plan fills.
- **Key discovery driving this plan:** `evals/answer_eval_full.py:122,130-132` derives the retrieval `category` from each item's **gold `namespace`** and passes it into `run_rag_query` — so the eval *forces* retrieval into the gold namespace and never runs the classifier. Consequence: an eval item mislabeled `namespace=soybeans` but actually asking about *Clearfield rice* or *pine seedlings* is force-retrieved into soybean chunks and **cannot** score correct. Several soybean-bucket items are exactly this (a Clearfield-rice question, a pine-seedling/forestry question, generic spray-math). The "14%" is measured on a partially-contaminated bucket.
- **Eval set + schema:** `evals/eval_set_v2.jsonl`, one JSON object per line with keys `query, chunk_id, chunk_text, document_title, namespace`. The gold answer chunk for an item is `chunk_id`.
- **How the sample is drawn:** `sample_items(items, n, seed=7)` from `evals/answer_eval.py`. Reusing it with the same n and seed reproduces the identical 20 items the dumps were scored on. Confirm n in Task 2 Step 2 by matching count to the 20-line dumps.
- **Index + embedder:** index name from env `PINECONE_INDEX_NAME` (currently `agroar-prod-gte-v3`), embedder `thenlper/gte-base` via `EMBEDDING_MODEL_PATH`. `.env` is at repo ROOT. Retrieval pattern to copy: `evals/eval_runner.py:150-164` (embed → `index.query(vector, top_k, namespace)` → read `m["id"]`) and `ingestion/spot_check.py`.
- **Cost:** Tasks 1–5 are **zero LLM cost** (local embedding + Pinecone queries only — same class as `spot_check.py`). The ONLY paid step is the optional Task 6 re-run, which is gated behind an explicit OK (user is cost-averse; one n=20 DeepInfra run ≈ $0.01–0.02).

---

## File Structure

- **Create `evals/retrieval_precision.py`** — the diagnostic. Pure helpers (`rank_of`, `classify_failure`, `join_dump`) with NO heavy module-level imports (so tests stay offline/fast); the network/sample/main logic imports `pinecone`/`sentence-transformers`/`answer_eval` *inside* `main()`.
- **Create `evals/test_retrieval_precision.py`** — pytest for the three pure helpers (offline, mocked inputs).
- **Create (output, gitignored) `evals/_retrieval_split.jsonl`** — one row per sampled item: `namespace, query, gold_chunk_id, hit5, rank, corr, faith, label, top_titles`.
- **Create `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md`** — the writeup: taxonomy counts, per-crop split, label-audit decisions, chosen next lever.
- **Create (output) `evals/eval_set_v2_clean.jsonl`** — eval set with audited namespace labels fixed; original `eval_set_v2.jsonl` is NEVER mutated.
- **Modify `PROGRESS.md`** — record the split result + decision (Task 5).

Add `evals/_retrieval_split.jsonl` to `.gitignore` alongside the existing `evals/_out_*.jsonl` / `evals/_log_*` ignore entries (commit `b7eab8d` added those — match that block).

---

### Task 1: Pure decision helpers (TDD)

**Files:**
- Create: `evals/retrieval_precision.py`
- Test: `evals/test_retrieval_precision.py`

- [ ] **Step 1: Write the failing test**

```python
# evals/test_retrieval_precision.py
"""Offline tests for the pure helpers in retrieval_precision.
No network, no model load — heavy imports live inside main()."""
from evals.retrieval_precision import rank_of, classify_failure, join_dump


def test_rank_of_found_first():
    assert rank_of("c3", ["c3", "c1", "c2"]) == 1

def test_rank_of_found_third():
    assert rank_of("c2", ["c0", "c1", "c2"]) == 3

def test_rank_of_missing_returns_none():
    assert rank_of("zzz", ["c0", "c1"]) is None

def test_rank_of_empty():
    assert rank_of("c0", []) is None


def test_classify_ok_when_correct():
    # corr >= 0.5 is a pass, never a failure label
    assert classify_failure(corr=1.0, faith=0.5, hit5=False) == "OK"
    assert classify_failure(corr=0.5, faith=0.0, hit5=False) == "OK"

def test_classify_retrieval_miss_when_gold_not_retrieved():
    assert classify_failure(corr=0.0, faith=0.5, hit5=False) == "RETRIEVAL_MISS"

def test_classify_gen_specificity_grounded_but_wrong():
    # gold chunk WAS retrieved, answer grounded (faith>=0.5) but wrong specifics
    assert classify_failure(corr=0.0, faith=0.5, hit5=True) == "GEN_SPECIFICITY"

def test_classify_gen_hallucination_retrieved_but_ungrounded():
    assert classify_failure(corr=0.0, faith=0.0, hit5=True) == "GEN_HALLUCINATION"


def test_join_dump_matches_by_query():
    dump = [{"query": "q1", "correctness": 0.0, "faithfulness": 0.5},
            {"query": "q2", "correctness": 1.0, "faithfulness": 1.0}]
    rec = join_dump("q2", dump)
    assert rec["correctness"] == 1.0 and rec["faithfulness"] == 1.0

def test_join_dump_missing_query_returns_none():
    assert join_dump("nope", [{"query": "q1"}]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo> && python -m pytest evals/test_retrieval_precision.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'rank_of'`.

- [ ] **Step 3: Write minimal implementation**

```python
# evals/retrieval_precision.py
"""Zero-LLM-cost retrieval/generation failure split.

Reproduces the seed=7 answer-eval sample, runs retrieval ONLY (local gte-base
embed + Pinecone top-5, no generation, no judge), and joins the gold chunk
hit@5/rank against the correctness/faithfulness already scored in the L2 dump.

Failure taxonomy per item:
  OK                : corr >= 0.5 (not a failure)
  RETRIEVAL_MISS    : corr < 0.5 AND gold chunk NOT in top-5  -> retrieval/corpus lever
  GEN_SPECIFICITY   : corr < 0.5 AND gold in top-5 AND faith >= 0.5 -> generation lever (L3: quote exact rate)
  GEN_HALLUCINATION : corr < 0.5 AND gold in top-5 AND faith < 0.5  -> generation/guard lever

Heavy imports (pinecone, sentence-transformers, answer_eval) are done inside
main() so the pure helpers below stay offline-testable.

Usage:
  cd <repo> && python -m evals.retrieval_precision \
      --eval-set evals/eval_set_v2.jsonl --sample 20 --seed 7 \
      --dump evals/_out_v3_L2on.jsonl --out evals/_retrieval_split.jsonl
"""
from __future__ import annotations


def rank_of(gold_id, ids):
    """1-based rank of gold_id in ids, or None if absent."""
    for i, x in enumerate(ids, 1):
        if x == gold_id:
            return i
    return None


def classify_failure(corr, faith, hit5):
    """Map a scored item to a failure-cause label. corr>=0.5 == pass == OK."""
    if corr >= 0.5:
        return "OK"
    if not hit5:
        return "RETRIEVAL_MISS"
    if faith >= 0.5:
        return "GEN_SPECIFICITY"
    return "GEN_HALLUCINATION"


def join_dump(query, dump):
    """Find the scored dump record for query (exact match), or None."""
    for r in dump:
        if r.get("query") == query:
            return r
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd <repo> && python -m pytest evals/test_retrieval_precision.py -v`
Expected: PASS — 10 passed.

- [ ] **Step 5: Commit**

```bash
git add evals/retrieval_precision.py evals/test_retrieval_precision.py
git commit -m "feat(evals): retrieval/generation failure-split pure helpers (TDD)"
```

---

### Task 2: Retrieval + sample-reproduction + dump-join `main()`

**Files:**
- Modify: `evals/retrieval_precision.py` (append `main()` and `if __name__` block)

- [ ] **Step 1: Append the runnable main()**

Append to `evals/retrieval_precision.py`:

```python
def _retrieve_ids(model, index, query, namespace, top_k):
    """Embed query with gte-base and return the top_k chunk ids from Pinecone.
    Mirrors evals/eval_runner.py:150-164 and ingestion/spot_check.py."""
    vec = model.encode(query, normalize_embeddings=True).tolist()
    res = index.query(vector=vec, top_k=top_k, namespace=namespace,
                      include_metadata=True)
    matches = res.get("matches", [])
    ids = [m["id"] for m in matches]
    titles = [m.get("metadata", {}).get("document_title", "?") for m in matches]
    return ids, titles


def main():
    import os, json, argparse
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    import torch
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone
    # reuse the EXACT sampler the answer-eval used, so we hit the same 20 items
    from evals.answer_eval import sample_items

    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", default="evals/eval_set_v2.jsonl")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--dump", default="evals/_out_v3_L2on.jsonl",
                    help="scored answer-eval dump to join corr/faith from")
    ap.add_argument("--out", default="evals/_retrieval_split.jsonl")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.eval_set, encoding="utf-8") if l.strip()]
    sample = sample_items(items, args.sample, seed=args.seed)
    dump = [json.loads(l) for l in open(args.dump, encoding="utf-8") if l.strip()]

    model_name = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)
    index_name = os.environ["PINECONE_INDEX_NAME"]
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(index_name)
    print(f"index={index_name} model={model_name} device={device} "
          f"sample={len(sample)} dump={len(dump)}")

    from collections import Counter
    counts = Counter()
    rows = []
    missing_in_dump = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for it in sample:
            ids, titles = _retrieve_ids(model, index, it["query"],
                                        it["namespace"], args.top_k)
            rank = rank_of(it["chunk_id"], ids)
            hit5 = rank is not None
            scored = join_dump(it["query"], dump)
            if scored is None:
                missing_in_dump += 1
                continue
            label = classify_failure(scored["correctness"],
                                     scored["faithfulness"], hit5)
            counts[label] += 1
            row = {
                "namespace": it["namespace"], "query": it["query"],
                "gold_chunk_id": it["chunk_id"], "hit5": hit5, "rank": rank,
                "corr": scored["correctness"], "faith": scored["faithfulness"],
                "label": label, "top_titles": titles,
            }
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nwrote {len(rows)} rows -> {args.out} "
          f"({missing_in_dump} sample items absent from dump)")
    print("\n=== FAILURE TAXONOMY (all crops) ===")
    for lbl in ["OK", "RETRIEVAL_MISS", "GEN_SPECIFICITY", "GEN_HALLUCINATION"]:
        print(f"  {lbl:18} {counts[lbl]}")
    print("\n=== PER-CROP label breakdown ===")
    by = {}
    for r in rows:
        by.setdefault(r["namespace"], Counter())[r["label"]] += 1
    for ns in sorted(by):
        c = by[ns]
        print(f"  {ns:9} " + "  ".join(f"{k}={c[k]}" for k in
              ["OK", "RETRIEVAL_MISS", "GEN_SPECIFICITY", "GEN_HALLUCINATION"]))
    print("\n=== soybean failing items (for label audit, Task 4) ===")
    for r in rows:
        if r["namespace"] == "soybeans" and r["label"] != "OK":
            print(f"  [{r['label']:16}] hit5={r['hit5']} rank={r['rank']} "
                  f"corr={r['corr']} :: {r['query'][:80]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run and confirm the sample matches the dump (zero LLM cost)**

Run: `cd <repo> && python -m evals.retrieval_precision --dump evals/_out_v3_L2on.jsonl`
Expected:
- First line prints `index=agroar-prod-gte-v3 ... sample=20 dump=20`.
- `wrote 20 rows ... (0 sample items absent from dump)` — **if `absent` > 0, the sampler/seed/n does not match the dump; STOP** and reconcile `--sample`/`--seed` until 0 absent (this proves we are analyzing the exact items that were scored). Try `--sample 20 --seed 7` first; if mismatch, inspect `evals/answer_eval.py:sample_items` for the n used by the dump run.
- A taxonomy table + per-crop breakdown + soybean audit list print.

- [ ] **Step 3: Commit the diagnostic + its first output**

```bash
git add evals/retrieval_precision.py .gitignore
git commit -m "feat(evals): retrieval-precision split runner (zero-cost, reproduces seed=7 sample)"
```

(Add `evals/_retrieval_split.jsonl` to the existing `evals/_out_*` ignore block in `.gitignore` in this same step.)

---

### Task 3: Record the split result in the findings doc

**Files:**
- Create: `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md`

- [ ] **Step 1: Capture the run output**

Run: `cd <repo> && python -m evals.retrieval_precision --dump evals/_out_v3_L2on.jsonl | tee evals/_retrieval_split.log`
Then also run once against the baseline: `python -m evals.retrieval_precision --dump evals/_out_v3_L2off.jsonl --out evals/_retrieval_split_L2off.jsonl | tee evals/_retrieval_split_L2off.log`

- [ ] **Step 2: Write the findings doc**

Create `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md` and paste BOTH taxonomy tables (L2-on and L2-off) verbatim from the logs. Then fill the interpretation using this exact rubric (no placeholders — write the real counts you observed):

```markdown
# Corpus-Gap Findings — Retrieval/Generation Split (2026-06-12)

## Method
Zero-LLM-cost. `evals/retrieval_precision.py` reproduced the seed=7 n=20 sample,
ran retrieval-only top-5 on `agroar-prod-gte-v3`, joined gold chunk hit@5 against
the correctness/faithfulness in `evals/_out_v3_L2on.jsonl`. Labels:
RETRIEVAL_MISS (gold not retrieved) / GEN_SPECIFICITY (gold retrieved, grounded,
wrong specifics) / GEN_HALLUCINATION (gold retrieved, ungrounded) / OK.

## Taxonomy (L2-on)  [paste table]
## Per-crop  [paste table]

## Read
- Dominant failure label = <X>. Therefore the next lever is <retrieval/corpus | generation L3>.
- RETRIEVAL_MISS count => how many failures are corpus/retrieval (gold chunk absent from top-5).
- GEN_SPECIFICITY count => how many are generation (right chunk in hand, wrong number/product) — fixable with an L3 "quote the exact rate/product from the cited chunk" directive, NO corpus work.
- Items flagged for label audit (Task 4): <list the soybean off-domain ones>.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/findings/2026-06-12-corpus-gap-findings.md
git commit -m "docs(evals): record retrieval/generation failure split findings"
```

---

### Task 4: Eval-set label audit → cleaned set

**Files:**
- Create: `evals/eval_set_v2_clean.jsonl`
- Modify: `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md` (append audit decisions)

- [ ] **Step 1: Print every sampled item with its label for eyeball review**

Run:
```bash
cd <repo> && python - <<'PY'
import json
from evals.answer_eval import sample_items
items = [json.loads(l) for l in open("evals/eval_set_v2.jsonl", encoding="utf-8") if l.strip()]
for it in sample_items(items, 20, seed=7):
    print(f'{it["namespace"]:9} | {it["document_title"][:40]:40} | {it["query"][:80]}')
PY
```

- [ ] **Step 2: Record an audit decision for each suspect item**

In `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md` append an "## Eval-set label audit" table. For each item where the query topic does NOT match its `namespace` (known suspects from prior inspection: the *Clearfield rice* question tagged soybeans, the *pine seedlings* forestry question, generic *spray-math / saddle-tank* questions), record one of: `KEEP` (label correct), `RELABEL <ns>` (wrong crop — fix namespace), or `DROP` (out of scope for rice/soy/poultry advisory, e.g. forestry). Decide from the query text + `document_title` only. Do not invent new items.

- [ ] **Step 3: Produce the cleaned eval set (original untouched)**

Write a one-off transform that applies the audit decisions to a COPY. Example skeleton — fill `DECISIONS` from the table you just wrote (keyed by a unique query substring), do not leave it empty:

```bash
cd <repo> && python - <<'PY'
import json
# query-substring -> ("relabel","rice") | ("drop",None) | ("keep",None)
DECISIONS = {
    "Clearfield rice": ("relabel", "rice"),
    "pine seedlings":  ("drop", None),
    # ... one entry per suspect item from the audit table ...
}
src = [json.loads(l) for l in open("evals/eval_set_v2.jsonl", encoding="utf-8") if l.strip()]
out = []
for it in src:
    action = ("keep", None)
    for sub, dec in DECISIONS.items():
        if sub.lower() in it["query"].lower():
            action = dec; break
    verb, arg = action
    if verb == "drop":
        continue
    if verb == "relabel":
        it = {**it, "namespace": arg}
    out.append(it)
with open("evals/eval_set_v2_clean.jsonl", "w", encoding="utf-8") as fh:
    for it in out:
        fh.write(json.dumps(it, ensure_ascii=False) + "\n")
print(f"clean set: {len(out)} items (was {len(src)})")
PY
```

Expected: prints the cleaned count (a few fewer than the original if any DROPs).

- [ ] **Step 4: Commit**

```bash
git add evals/eval_set_v2_clean.jsonl docs/superpowers/findings/2026-06-12-corpus-gap-findings.md
git commit -m "chore(evals): audited eval-set labels -> eval_set_v2_clean.jsonl"
```

---

### Task 5: Decision + PROGRESS.md update (no code)

**Files:**
- Modify: `PROGRESS.md`

- [ ] **Step 1: Write the decision into PROGRESS.md**

Add a dated section at the top of `PROGRESS.md` (above the most recent section) stating: (a) the taxonomy split counts, (b) the chosen next lever derived from the dominant label — **if GEN_SPECIFICITY dominates → next = L3 "quote exact rate/product from cited chunk" generation lever; if RETRIEVAL_MISS dominates → next = corpus coverage / re-ingest for the missing topics**, and (c) that suppression is confirmed 0% so guard work is closed. Convert any relative dates to absolute (2026-06-12).

- [ ] **Step 2: Commit**

```bash
git add PROGRESS.md
git commit -m "docs(progress): corpus-gap split result + next lever chosen"
```

(Pushing `main` here is fine — none of these files touch `backend/**`, so the HF deploy Action will NOT fire. Verify with `git show --stat HEAD` before push.)

---

### Task 6 (OPTIONAL, PAID — get explicit OK first): re-measure on the cleaned set

**Do not run without owner approval.** One n=20 DeepInfra run ≈ $0.01–0.02. Only worth it if Task 4 produced DROP/RELABEL changes large enough to plausibly move the honest soybean number, AND the owner wants the cleaned headline figure.

- [ ] **Step 1: Confirm cost + get OK** (state the per-run cost, wait for yes).

- [ ] **Step 2: Re-run answer eval on the cleaned set**

Run: `cd <repo> && python evals/answer_eval_full.py --eval-set evals/eval_set_v2_clean.jsonl --sample 20 --seed 7 --provider deepinfra --dump evals/_out_v3_clean.jsonl`
Expected: per-namespace correctness table; soybean correctness should rise if mislabeled items were removed.

- [ ] **Step 3: Record the cleaned headline number in `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md` and `PROGRESS.md`; commit.**

```bash
git add docs/superpowers/findings/2026-06-12-corpus-gap-findings.md PROGRESS.md
git commit -m "docs(evals): cleaned-set headline correctness (paid re-run)"
```

---

## Self-Review notes (for the executor)

- **If Task 2 Step 2 reports `absent > 0`:** the sample doesn't match the dump — fix `--sample`/`--seed` before trusting any split. The whole analysis depends on hitting the same 20 items.
- **`classify_failure` rubric is the load-bearing logic** — its four branches are exactly the four engineering levers. Don't add fuzzy middle categories; corr>=0.5 is OK, everything else routes by (hit5, faith).
- **Never mutate `evals/eval_set_v2.jsonl`** — all label fixes go to `eval_set_v2_clean.jsonl`.
- **Zero-cost guarantee:** Tasks 1–5 make no LLM API calls (embedding is the *local* gte-base model; Pinecone queries are free-tier reads). Only Task 6 spends, and it's gated.
- **Guardrail check:** this plan does NOT propose a retrieval-*technique* swap (BM25/HyDE/reranker — all rejected). It measures whether the gap is corpus-coverage, eval-label noise, or generation-specificity. Those are new, un-rejected levers.
```
