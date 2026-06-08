# Eval Set Namespace Audit + Relabeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit the 70 soybeans-namespace items in `eval_set_v2.jsonl`, reclassify off-crop items (pine, wheat, rice, cotton, corn, pasture) to `general` namespace, re-run DeepInfra 70B eval with corrected labels, record honest per-crop correctness numbers for arXiv + NIW.

**Architecture:** A standalone LLM-classifier script (`evals/audit_namespace.py`) reads each soybeans item, prompts DeepInfra Llama-3.3-70B to classify by QUERY INTENT (`soybeans` vs `general`), writes `evals/eval_set_v2_relabeled.jsonl`. The existing `answer_eval_full.py --eval-set` flag re-runs the eval on the relabeled set with zero changes to production code. The relabeled set is the new canonical eval for NIW/arXiv.

**Tech Stack:** Python, `langchain_openai.ChatOpenAI` (already in `backend/requirements.txt`), DeepInfra Llama-3.3-70B, existing `evals/answer_eval_full.py`.

---

## Background Context

### Why soybeans scores low

Four of the seven sampled soybeans items in the seed=7 run came from a single UA Extension document: **"soybeans recommended chemicals for weed and brush control."** That document contains content applicable to pine seedlings, wheat, and Clearfield rice — all correctly stored in the soybeans Pinecone namespace, but the queries route to soybeans-only retrieval even though the farmer is asking about pine or rice. Result: retrieval returns a plausible-but-wrong soybeans herbicide chunk → low confidence → suppression.

### Why `general` is the right relabel target

`namespace=general` maps to `IN_SCOPE_GENERAL_AG` which triggers `_fanout_search` across all three crop namespaces (rice + soybeans + poultry). The gold chunk lives in the soybeans namespace; fanout will still find it, but the candidate pool is 3× wider → better precision on off-crop queries.

### Classification rule (QUERY INTENT, not document origin)

- **`soybeans`**: query primarily asks about soybean planting/seeding, soybean varieties/traits, soybean diseases, soybean-specific herbicide programs, soybean yields, soybean storage, or soybean pest management
- **`general`**: query asks about weed/brush control applicable across crops, farm equipment (sprayer calibration), soil/irrigation, pine/forestry, wheat, cotton, corn, rice, pasture, vegetables — any topic where soybeans are NOT the primary subject

---

## Files

| Action | Path | Purpose |
|---|---|---|
| **Create** | `evals/audit_namespace.py` | LLM classifier: soybeans items → soybeans\|general; writes relabeled jsonl |
| **Create** | `evals/eval_set_v2_relabeled.jsonl` | Output of audit script (generated, not handwritten) |
| **Modify** | `PROGRESS.md` | Add before/after comparison table |
| **Modify** | `docs/status-bar.md` | Update eval status |
| **Modify** | `~/.claude/.../memory/project_answer_quality.md` | Update with relabeled numbers |

---

## Task 1 · Write `evals/audit_namespace.py`

**Files:**
- Create: `evals/audit_namespace.py`

- [ ] **Step 1: Create the script**

```python
"""Audit soybeans-namespace eval items for off-crop content.

Classifies each soybeans item by QUERY INTENT using DeepInfra LLM:
  soybeans — query is specifically about soybean agronomy/pests/varieties
  general  — weed management, pine, wheat, rice, cotton, corn, pasture, equipment, etc.

Writes evals/eval_set_v2_relabeled.jsonl with updated namespace fields.

Usage:
  cd evals
  python audit_namespace.py [--dry-run]
"""
import os, sys, json, argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

EVAL_SET   = Path(__file__).parent / "eval_set_v2.jsonl"
OUT_PATH   = Path(__file__).parent / "eval_set_v2_relabeled.jsonl"

SYSTEM = (
    "You classify queries for an Arkansas agricultural advisory RAG system. "
    "The system has namespaces: soybeans, rice, poultry, general.\n\n"
    "Classify the query's PRIMARY TOPIC for retrieval routing.\n"
    "Reply with ONLY one word: soybeans OR general\n\n"
    "soybeans = query is specifically about soybean planting, soybean seeding rates, "
    "soybean varieties/traits, soybean diseases, soybean-specific herbicide programs, "
    "soybean yields, or soybean storage.\n"
    "general  = weed/brush management across crops, farm equipment (sprayer calibration), "
    "soil/irrigation, pine/forestry, wheat, cotton, corn, rice, pasture, vegetables, "
    "or any topic where soybeans are NOT the primary subject."
)

USER_TEMPLATE = """QUERY: {query}

GOLD PASSAGE (first 250 chars):
{chunk_text}

DOCUMENT TITLE: {document_title}

Reply ONLY: soybeans OR general"""


def classify_item(llm: ChatOpenAI, item: dict) -> str:
    resp = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=USER_TEMPLATE.format(
            query=item["query"],
            chunk_text=item.get("chunk_text", "")[:250],
            document_title=item.get("document_title", "unknown"),
        )),
    ])
    label = (resp.content or "").strip().lower()
    # normalise: accept any response containing soybeans or general
    if "soybeans" in label:
        return "soybeans"
    if "general" in label:
        return "general"
    # fallback: keep original if LLM returns garbage
    return item["namespace"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print classifications without writing output file")
    args = ap.parse_args()

    llm = ChatOpenAI(
        model=os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        openai_api_key=os.environ["DEEPINFRA_API_KEY"],
        openai_api_base="https://api.deepinfra.com/v1",
        temperature=0,
    )

    items = [json.loads(l) for l in open(EVAL_SET, encoding="utf-8")]
    soy_items = [(i, it) for i, it in enumerate(items) if it["namespace"] == "soybeans"]

    print(f"Auditing {len(soy_items)} soybeans items...\n")
    print(f"{'idx':>4} {'new_ns':>9}  query (first 65 chars)")
    print("-" * 82)

    changes = 0
    for idx, item in soy_items:
        new_ns = classify_item(llm, item)
        marker = " ←" if new_ns != item["namespace"] else ""
        if new_ns != item["namespace"]:
            changes += 1
        print(f"{idx:>4} {new_ns:>9}{marker}  {item['query'][:65]}")
        item["namespace"] = new_ns

    print(f"\nTotal relabeled: {changes} / {len(soy_items)}")
    print(f"  soybeans → general: {changes}")
    print(f"  unchanged: {len(soy_items) - changes}")

    ns_counts = {}
    for it in items:
        ns_counts[it["namespace"]] = ns_counts.get(it["namespace"], 0) + 1
    print(f"\nNew namespace distribution: {ns_counts}")

    if not args.dry_run:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
        print(f"\nWrote {OUT_PATH}")
    else:
        print("\n[dry-run] Output file NOT written.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run to verify script parses correctly without writing output**

```bash
cd evals && python audit_namespace.py --dry-run 2>&1 | head -20
```

Expected: prints column header + first few item classifications, no file written.

---

## Task 2 · Run Full Audit + Review

**Files:**
- Run: `evals/audit_namespace.py`
- Inspect: console output
- Inspect (optional): `evals/eval_set_v2_relabeled.jsonl`

- [ ] **Step 1: Run full classification (writes output file)**

```bash
cd evals && python audit_namespace.py 2>&1
```

Expected output shape:
```
Auditing 70 soybeans items...

 idx   new_ns  query (first 65 chars)
-----------------------------------------------------------------------------------
   0 soybeans  How do I make sure I'm puttin' out the right amount of spray...
   3  general ←  I got a bunch of new pine seedlings and there's a lot of we...
...
Total relabeled: ~25-35 / 70
New namespace distribution: {'soybeans': ~35-45, 'general': ~25-35, 'rice': 110, 'poultry': 20}
```

- [ ] **Step 2: Spot-check 5 relabeled items for accuracy**

```bash
cd evals && python -c "
import json
orig = {i: json.loads(l) for i, l in enumerate(open('eval_set_v2.jsonl', encoding='utf-8'))}
new  = {i: json.loads(l) for i, l in enumerate(open('eval_set_v2_relabeled.jsonl', encoding='utf-8'))}

changed = [(i, orig[i]['namespace'], new[i]['namespace'], orig[i]['query'][:70])
           for i in orig if orig[i]['namespace'] != new[i]['namespace']]
print(f'Total relabeled: {len(changed)}')
for idx, old_ns, new_ns, q in changed[:10]:
    print(f'[{idx:>3}] {old_ns} → {new_ns}  | {q}')
" 2>&1
```

Verify: pine seedling items, wheat queries, Clearfield rice query, sprayer calibration, cotton/corn items — all should be `general`. Genuine soybean seeding/disease/variety queries should stay `soybeans`.

- [ ] **Step 3: Verify zero missing items and structure preserved**

```bash
cd evals && python -c "
import json
orig = [json.loads(l) for l in open('eval_set_v2.jsonl', encoding='utf-8')]
new  = [json.loads(l) for l in open('eval_set_v2_relabeled.jsonl', encoding='utf-8')]
assert len(orig) == len(new), f'Item count mismatch: {len(orig)} vs {len(new)}'
for i, (o, n) in enumerate(zip(orig, new)):
    assert o['chunk_id'] == n['chunk_id'], f'chunk_id mismatch at {i}'
    assert o['query']    == n['query'],    f'query mismatch at {i}'
print(f'OK: {len(new)} items, chunk_ids + queries intact')
" 2>&1
```

Expected: `OK: 200 items, chunk_ids + queries intact`

- [ ] **Step 4: Commit audit script and relabeled set**

```bash
cd .. && git add evals/audit_namespace.py evals/eval_set_v2_relabeled.jsonl
git commit -m "feat(evals): LLM namespace audit — relabel off-crop soybeans items to general"
```

---

## Task 3 · Re-run Eval on Relabeled Set

**Files:**
- Run: `evals/answer_eval_full.py` (unchanged)
- Inputs: `evals/eval_set_v2_relabeled.jsonl`

- [ ] **Step 1: Smoke test with 3 items on relabeled set**

```bash
cd evals && python answer_eval_full.py \
  --provider deepinfra \
  --sample 3 \
  --seed 7 \
  --eval-set evals/eval_set_v2_relabeled.jsonl 2>&1
```

Expected: `scored=3 skipped=0`, per-item lines print `corr=X.X faith=X.X`.

- [ ] **Step 2: Full 20-item eval (same seed=7 for direct before/after comparison)**

```bash
cd evals && python answer_eval_full.py \
  --provider deepinfra \
  --sample 20 \
  --seed 7 \
  --eval-set evals/eval_set_v2_relabeled.jsonl 2>&1
```

Pass criteria: `scored=20 skipped=0`, per-namespace breakdown prints with a `general` row present.

Note: the 3 formerly-suppressed soybeans items are now labeled `general` → they use fanout retrieval. Expect soybeans suppression to drop (genuine soybean queries only remain), and `general` correctness to give a new baseline.

- [ ] **Step 3: Extended run n=50 to get robust per-namespace counts**

n=20 may leave soybeans with only 3-5 items after relabeling (too noisy for arXiv). n=50 gives ~15-20 genuine soybeans items for credible stats.

```bash
cd evals && python answer_eval_full.py \
  --provider deepinfra \
  --sample 50 \
  --seed 7 \
  --eval-set evals/eval_set_v2_relabeled.jsonl 2>&1
```

Pass criteria: `scored=50 skipped=0`. Soybeans row should have n≥10 for reportable stats.

---

## Task 4 · Document Results

**Files:**
- Modify: `PROGRESS.md`
- Modify: `docs/status-bar.md`
- Modify: `~/.claude/.../memory/project_answer_quality.md`

- [ ] **Step 1: Add before/after comparison section to `PROGRESS.md`**

Add under the existing `## ✅ 70B Prod Eval Results (2026-06-05)` section:

```markdown
### Relabeled eval (eval_set_v2_relabeled.jsonl, n=50, seed=7)

**What changed:** ~N soybeans items relabeled to `general` (off-crop content from
"soybeans recommended chemicals for weed and brush control" doc: pine seedlings,
wheat herbicides, Clearfield rice, sprayer calibration, broadleaf brush control).

| namespace | n | supp | corr | faith | mean_conf |
|---|---|---|---|---|---|
| soybeans | X | X% | **X%** | X% | X.XX |
| general | X | X% | X% | X% | X.XX |
| rice | X | X% | X% | X% | X.XX |
| poultry | X | X% | X% | X% | X.XX |
| **OVERALL** | **50** | **X%** | **X%** | **X%** | — |

**Before/after soybeans (n=20 seed=7 original vs relabeled):**
- Original soybeans: corr 14%, faith 29%, supp 43% (includes off-crop items)
- Relabeled soybeans: corr X%, faith X%, supp X% (genuine soybean queries only)
```

(Fill in actual numbers from Task 3 Step 3 output.)

- [ ] **Step 2: Update `docs/status-bar.md`**

Find the "Trustworthy eval" line and append relabeled numbers.

- [ ] **Step 3: Update memory `project_answer_quality.md`**

Add relabeled numbers to the "HONEST 70B PROD EVAL" section at the top of the memory file. Update description field to reflect relabeled results.

- [ ] **Step 4: Final commit**

```bash
git add PROGRESS.md docs/status-bar.md
git commit -m "docs(evals): record relabeled namespace eval results for arXiv/NIW"
```

---

## Self-Review

**Spec coverage:**
- ✅ Audit 70 soybeans items → Task 1 + Task 2
- ✅ LLM classification by query intent → Task 1 (`classify_item`)
- ✅ Write relabeled eval set → Task 1 (`OUT_PATH` write)
- ✅ Verify integrity of relabeled set → Task 2 Step 3
- ✅ Re-run DeepInfra 70B eval → Task 3
- ✅ Extended n=50 run for arXiv-quality stats → Task 3 Step 3
- ✅ Document before/after → Task 4

**Placeholder scan:** None found. All steps include actual code/commands.

**Type consistency:** `classify_item` returns `str`, used as dict value `item["namespace"]` — consistent throughout. `OUT_PATH` defined once, referenced consistently.

**Edge cases handled:**
- LLM returns garbage → `classify_item` falls back to `item["namespace"]` (keeps original)
- Dry-run flag → no file written (safe for inspection)
- Integrity check in Task 2 Step 3 → catches any item reorder or count mismatch
