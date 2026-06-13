# Rice Diagnosis + B2 Format-Tax Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find out why rice correctness is stuck at 18% while every lever moves the other crops, then run the B2 format-tax probe to decide whether JSON-constrained decoding (not 70B capability) is the remaining generation ceiling.

**Architecture:** Two measure-first investigations, ordered cheapest-first: Task 1 is a zero-cost read of existing eval dumps (rice failure classification → may re-aim B2); Tasks 2–3 add an eval-only `--two-step` flag to `evals/answer_eval_full.py` (same prompt, UNCONSTRAINED decoding, parse-or-repair to schema) and run one paired n=40 arm against the existing B1-on dump. Task 4 closes or keeps the B3 `source_quote` lever using grounding data the new flag adds to dumps. No production code changes anywhere in this plan.

**Tech Stack:** Python 3.13, pytest, LangChain (`ChatOpenAI` DeepInfra / `ChatGroq` 8b-instant repair formatter), existing eval harness (`evals/answer_eval_full.py`, independent Gemini judge via `--judge-provider gemini`).

---

## Context for an engineer with zero repo history (READ FIRST)

- **Read `PROGRESS.md` top section before starting.** Single source of truth. This plan continues `docs/superpowers/plans/2026-06-12-answer-quality-next-lever.md` (EXECUTED — Phase A + B1 shipped).
- **The trustworthy metric series** (only compare against these, never the old self-judged 35%): clean set `evals/eval_set_v2_clean.jsonl` (198 items), DeepInfra 70B generation, **independent Gemini judge** (`--judge-provider gemini`), n=40 seed=7, index `agroar-prod-gte-v3`:
  - baseline (B1 off): corr 23.8% / faith 57.5% — dump `evals/_out_clean_indepjudge.jsonl`
  - B1 on (now prod default): corr 27.5% / faith 65.0% — dump `evals/_out_clean_indepjudge_b1on.jsonl`
  - per-crop corr (B1 on): poultry 25% (n=4), **rice 18% (n=19, FLAT across all levers)**, soybeans 38% (n=17)
- **Durable guardrails (do NOT violate):**
  1. No retrieval-technique levers (5 tested + rejected). RETRIEVAL_MISS labels in splits are ~85% artifact on this corpus (yearly-series near-duplicate docs).
  2. Citation guard is closed (0% suppression). Don't reopen.
  3. **Every paid eval run is cost-gated: state the $ estimate and get Taiwo's OK first.** One n=40 DeepInfra+Gemini run ≈ $0.05–0.10.
  4. Conventional Commits; NEVER add Co-Authored-By trailers.
- **`.env` lives at repo ROOT.** Local `PINECONE_INDEX_NAME` may be stale at v2 — always pass `PINECONE_INDEX_NAME=agroar-prod-gte-v3` as an env prefix on eval runs.
- **Run eval scripts with `python -u`** (unbuffered) so per-item lines stream to the log.
- Evals-only changes do NOT trigger the HF backend deploy Action (it watches `backend/**`), so pushing this work does not redeploy prod.

---

### Task 1: Rice failure diagnosis (zero-cost, read-only — DO FIRST, it may re-aim B2)

Rice has the biggest item mass (n=19) and didn't move under L2/L3/B1 while poultry (+13pp) and soybeans (+6pp) did. Classify every failing rice item before spending on B2.

**Files:**
- Create: `docs/superpowers/2026-06-13-rice-diagnosis-findings.md`
- Read-only inputs: `evals/_out_clean_indepjudge_b1on.jsonl`, `evals/_out_clean_indepjudge.jsonl`, `evals/_retrieval_split_clean.jsonl`

- [ ] **Step 1: Dump every failing rice item with its split label and judge rationales**

Run from repo root:

```bash
python -c "
import json
on={r['query']:r for r in map(json.loads,open('evals/_out_clean_indepjudge_b1on.jsonl',encoding='utf-8'))}
split={r['query']:r for r in map(json.loads,open('evals/_retrieval_split_clean.jsonl',encoding='utf-8'))}
i=0
for q,r in on.items():
    if r['namespace']!='rice' or r['correctness']>=1.0: continue
    i+=1; s=split.get(q,{})
    print(f'--- RICE FAIL {i} corr={r[\"correctness\"]} faith={r[\"faithfulness\"]} label={s.get(\"label\",\"?\")} hit5={s.get(\"hit5\",\"?\")}')
    print(f'  q: {q}')
    print(f'  gold_doc: {s.get(\"gold_doc\",\"?\")}')
    print(f'  corr_rationale: {r[\"corr_rationale\"]}')
    print(f'  faith_rationale: {r[\"faith_rationale\"]}')
    print(f'  top_titles: {s.get(\"top_titles\",[])[:3]}')
" > evals/_rice_fails.txt
cat evals/_rice_fails.txt
```

Expected: ~15 rice items (19 minus the ~3-4 scoring 1.0) with full rationales.

- [ ] **Step 2: Hand-classify each failing item into exactly one bucket**

Read each item's query + rationales + gold_doc + top_titles. Buckets:

| bucket | signature | example from the n=40 audit |
|---|---|---|
| `GOLD_ARTIFACT` | answer is plausibly correct but judged against a single gold passage it didn't use (faith ≥ 0.5, corr_rationale says "fails to use the reference" / gold_doc is a yearly "br wells" research-study volume) | potassium question, gold = "2023 br wells", retrieved the dedicated potassium doc |
| `EVAL_MISLABEL` | the query itself doesn't belong (wrong crop/namespace, out-of-scope) | "My soybean yields are down…" sitting in the rice namespace |
| `GEN_FAILURE` | right docs in top_titles, but the answer states wrong/invented numbers or products (corr_rationale says "hallucinates") | invented "bin drying method" item |
| `TRUE_RETRIEVAL` | no on-topic doc in top_titles AND gold_doc is a real dedicated doc (not a yearly volume) | metribuzin-tolerance analog |

- [ ] **Step 3: Write the findings doc**

Create `docs/superpowers/2026-06-13-rice-diagnosis-findings.md` with: the bucket count table, one line per item (bucket + 10-word reason), and a **decision paragraph** answering:

- If `GEN_FAILURE` ≥ ~50% of rice failures → proceed to Task 2/3 unchanged (B2 attacks generation).
- If `GOLD_ARTIFACT` + `EVAL_MISLABEL` ≥ ~50% → rice 18% is substantially an EVAL problem, not a pipeline problem. Still run B2 (it reads on all crops), but ALSO add a follow-up recommendation: curate `eval_set_v2_clean.jsonl` rice items (relabel/drop, same procedure as the soybean audit that produced the clean set) before trusting any rice headline.
- If `TRUE_RETRIEVAL` dominates → STOP and report to Taiwo before doing anything (would contradict the closed-retrieval guardrail; do not build retrieval levers without his call).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/2026-06-13-rice-diagnosis-findings.md
git commit -m "docs(evals): rice failure diagnosis - bucket classification of 18%-corr rice items"
```

---

### Task 2: B2 `--two-step` flag in the eval harness (TDD, $0, no prod code)

**What B2 tests:** prod generates the whole advisory in ONE `with_structured_output(AdvisoryDraft, method="json_mode")` call = constrained decoding. Literature (Tam et al. 2024, "Let Me Speak Freely?") measures ~10–15pp reasoning loss from format-constrained decoding. The probe: identical prompt, identical model, but **unconstrained** generation → parse the JSON it emits freely → on parse failure, one free Groq 8b-instant repair call formats it. This isolates the decoding constraint as the single variable (NOT a prose-CoT rewrite — that would confound prompt changes).

**Files:**
- Modify: `evals/answer_eval_full.py`
- Test: `evals/tests/test_two_step.py` (new)
- Create: `evals/paired_compare.py` (small reporting script, reused by Task 3/4)

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_two_step.py`:

```python
"""B2 format-tax probe: unconstrained generation + parse-or-repair to AdvisoryDraft.

All offline — no API calls. The repair path is exercised with a fake formatter."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from evals.answer_eval_full import extract_json_block, _TwoStepRunnable, _TwoStepLLM


VALID = {
    "response_type": "diagnostic", "problem_summary": "x",
    "confidence": "High", "confidence_explanation": "y", "language": "en",
    "context_meta": {"soil_data_available": False,
                     "weather_data_available": False, "county_fips": "05031"},
}


class _FakeMsg:
    def __init__(self, content): self.content = content


class _FakeLLM:
    def __init__(self, content): self._content = content
    async def ainvoke(self, messages, config=None): return _FakeMsg(self._content)


def test_extract_json_block_plain():
    assert extract_json_block(json.dumps(VALID))["problem_summary"] == "x"


def test_extract_json_block_fenced():
    raw = "Here is the advisory:\n```json\n" + json.dumps(VALID) + "\n```\nDone."
    assert extract_json_block(raw)["problem_summary"] == "x"


def test_extract_json_block_garbage_returns_none():
    assert extract_json_block("no json here at all") is None


def test_two_step_runnable_parses_free_output():
    r = _TwoStepRunnable(_FakeLLM(json.dumps(VALID)), repair_llm=None)
    draft = asyncio.run(r.ainvoke([]))
    assert draft.problem_summary == "x"
    assert draft.analysis is None or isinstance(draft.analysis, str)


def test_two_step_runnable_uses_repair_on_unparseable():
    from models.advisory import AdvisoryDraft
    repaired = AdvisoryDraft(**VALID)

    class _FakeRepair:
        async def ainvoke(self, messages, config=None): return repaired

    r = _TwoStepRunnable(_FakeLLM("prose with no JSON"), repair_llm=_FakeRepair())
    draft = asyncio.run(r.ainvoke([]))
    assert draft.problem_summary == "x"


def test_two_step_llm_wraps_with_structured_output():
    wrapper = _TwoStepLLM(_FakeLLM(json.dumps(VALID)))
    runnable = wrapper.with_structured_output(object, method="json_mode")
    assert isinstance(runnable, _TwoStepRunnable)
```

- [ ] **Step 2: Run tests, verify they fail on import**

```bash
python -m pytest evals/tests/test_two_step.py -q
```

Expected: `ImportError: cannot import name 'extract_json_block'`.

- [ ] **Step 3: Implement in `evals/answer_eval_full.py`**

Add after the existing `_parse_score` helper:

```python
def extract_json_block(raw: str) -> dict | None:
    """Pull the first JSON object out of free-form model output (handles ```json
    fences and surrounding prose). None when nothing parseable is found."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1].lstrip("json").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


class _TwoStepRunnable:
    """Drop-in for the runnable with_structured_output returns: generates
    UNCONSTRAINED (no response_format), then parses; one repair call on failure."""

    def __init__(self, llm, repair_llm):
        self._llm = llm
        self._repair = repair_llm

    async def ainvoke(self, messages, config=None):
        from models.advisory import AdvisoryDraft
        resp = await self._llm.ainvoke(messages, config=config)
        parsed = extract_json_block(getattr(resp, "content", "") or "")
        if parsed is not None:
            try:
                return AdvisoryDraft(**parsed)
            except Exception:
                pass
        if self._repair is None:
            raise ValueError("two-step: unparseable output and no repair LLM")
        from langchain_core.messages import HumanMessage
        return await self._repair.ainvoke([HumanMessage(content=(
            "Convert this agricultural advisory into the AdvisoryResponse JSON "
            "schema. Copy every rate, product name, threshold, and citation "
            "title EXACTLY as written - do not invent or drop content.\n\n"
            f"ADVISORY:\n{getattr(resp, 'content', '')[:8000]}"
        ))], config=config)


class _TwoStepLLM:
    """Wraps the generation LLM so rag.py's llm.with_structured_output(...) hands
    back our unconstrained-then-parse runnable instead of constrained decoding."""

    def __init__(self, llm, repair_llm=None):
        self._llm = llm
        self._repair = repair_llm

    def with_structured_output(self, schema, **kwargs):
        return _TwoStepRunnable(self._llm, self._repair)
```

- [ ] **Step 4: Wire the CLI flag**

In `main()`, add the argparse line next to `--judge-provider`:

```python
    ap.add_argument("--two-step", action="store_true",
                    help="B2 format-tax probe: unconstrained generation, then "
                         "parse (one Groq 8b repair call on failure). Requires "
                         "--provider deepinfra.")
```

After the `args.judge_provider` block (and BEFORE the `args.no_guard` check), add:

```python
    if args.two_step:
        if args.provider != "deepinfra":
            raise SystemExit("--two-step currently supports --provider deepinfra only.")
        from langchain_openai import ChatOpenAI
        from langchain_groq import ChatGroq
        from models.advisory import AdvisoryDraft
        _free_llm = ChatOpenAI(
            model=os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
            openai_api_key=os.environ["DEEPINFRA_API_KEY"],
            openai_api_base="https://api.deepinfra.com/v1",
            temperature=0.1,
        )
        _repair = ChatGroq(
            model="llama-3.1-8b-instant", api_key=os.environ["GROQ_API_KEY"],
            temperature=0,
        ).with_structured_output(AdvisoryDraft, method="json_mode")
        # Pre-seed rag's cached deepinfra client so run_rag_query generates
        # through the wrapper (rag._get_deepinfra_llm returns the cached global).
        rag._deepinfra_llm = _TwoStepLLM(_free_llm, repair_llm=_repair)
```

Also extend the run banner print to include it:

```python
    print(f"provider={args.provider}  judge={args.judge_provider}  "
          f"two_step={args.two_step}  guard={'off' if args.no_guard else 'on'}  bridge={args.bridge}")
```

- [ ] **Step 5: Add grounding fields to the dump row (for Task 4's B3 decision)**

In `evaluate()`, extend the returned dict with two keys after `"citations"`:

```python
        "products_rates": adv.get("products_rates"),
        "chunk_snippets": [(c.get("snippet") or "")[:500] for c in chunks],
```

- [ ] **Step 6: Run the tests, verify green; full evals suite stays green**

```bash
python -m pytest evals/tests/test_two_step.py -q
python -m pytest evals/tests -q
```

Expected: 6 pass; full evals suite passes (77+ before this task).

- [ ] **Step 7: Create `evals/paired_compare.py`**

```python
"""Paired helped/hurt comparison between two answer-eval dumps (joined on query).

Usage: python evals/paired_compare.py evals/_out_A.jsonl evals/_out_B.jsonl
Prints overall means, per-namespace means, and helped/hurt/same per metric
(A = first file = treatment arm, B = second file = control arm)."""
import json
import sys


def load(path):
    return {r["query"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    keys = [q for q in a if q in b]
    print(f"paired n = {len(keys)}  (A={sys.argv[1]}  B={sys.argv[2]})")
    for metric in ("correctness", "faithfulness"):
        ma = sum(a[q][metric] for q in keys) / len(keys)
        mb = sum(b[q][metric] for q in keys) / len(keys)
        helped = [q for q in keys if a[q][metric] > b[q][metric]]
        hurt = [q for q in keys if a[q][metric] < b[q][metric]]
        print(f"{metric}: B {100*mb:.1f}% -> A {100*ma:.1f}%  "
              f"(helped {len(helped)} / hurt {len(hurt)} / same {len(keys)-len(helped)-len(hurt)})")
        for q in hurt:
            print(f"   HURT [{b[q]['namespace']}] {b[q][metric]}->{a[q][metric]} :: {q[:70]}")
    by_ns = {}
    for q in keys:
        by_ns.setdefault(a[q]["namespace"], []).append(q)
    for ns, qs in sorted(by_ns.items()):
        ca = sum(a[q]["correctness"] for q in qs) / len(qs)
        cb = sum(b[q]["correctness"] for q in qs) / len(qs)
        print(f"  {ns:9} n={len(qs):2}  corr B {100*cb:.0f}% -> A {100*ca:.0f}%")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Commit**

```bash
git add evals/answer_eval_full.py evals/tests/test_two_step.py evals/paired_compare.py
git commit -m "feat(evals): --two-step format-tax probe (B2) + paired_compare reporter"
```

---

### Task 3: Run the B2 paired arm (COST-GATED — get Taiwo's OK first)

- [ ] **Step 1: State the cost and get the OK**

Tell Taiwo: "B2 probe run: n=40, DeepInfra 70B unconstrained + Gemini judge, ~$0.05–0.10 (repair calls are free Groq). OK?" **Do not run without the OK.**

- [ ] **Step 2: Run (background, unbuffered, absolute paths)**

```bash
cd <repo-root>
PINECONE_INDEX_NAME=agroar-prod-gte-v3 python -u evals/answer_eval_full.py \
  --provider deepinfra --eval-set evals/eval_set_v2_clean.jsonl \
  --sample 40 --seed 7 --judge-provider gemini --two-step \
  --dump evals/_out_clean_indepjudge_twostep.jsonl 2>&1 | tee evals/_phaseB2_run.log
```

~25–40 min. B1 is default-ON so it is active in BOTH arms (control = the existing B1-on dump) — the only variable is the decoding constraint. Watch the first 3 items: if they all log `SKIPPED`, kill the run and debug the wrapper before burning 40 generations.

- [ ] **Step 3: Paired comparison against the B1-on control arm**

```bash
python evals/paired_compare.py evals/_out_clean_indepjudge_twostep.jsonl evals/_out_clean_indepjudge_b1on.jsonl
```

- [ ] **Step 4: Read the verdict**

| outcome | meaning | action |
|---|---|---|
| corr ≥ +5pp AND helped > hurt | format tax is real on this stack | write a NEW plan to productionize two-step generation in `backend/services/rag.py` (latency + streaming UX implications — do NOT bolt it in under this plan). **Phase C (model swap) is dead.** |
| corr within ±5pp | format tax disproven for this stack | B2 closed. Phase C (model swap) becomes the live next question — that is Taiwo's call (ongoing prod cost), present numbers and stop. |
| corr ≤ −5pp | constrained decoding is HELPING (schema scaffolds the 70B) | B2 closed, document the negative result (it's publishable methodology either way). |

Also check `grep -c SKIPPED evals/_phaseB2_run.log` — a high skip count means parse+repair failures and the arm's numbers are not trustworthy; report rather than conclude.

- [ ] **Step 5: Commit the run log reference + result into the findings doc**

Append a "B2 result" section to `docs/superpowers/2026-06-13-rice-diagnosis-findings.md` with the table from Step 4 and the per-crop deltas (did rice finally move?).

```bash
git add docs/superpowers/2026-06-13-rice-diagnosis-findings.md
git commit -m "docs(evals): B2 format-tax probe result - <one-line verdict>"
```

---

### Task 4: B3 redundancy decision (zero-cost, closes or keeps the source_quote lever)

B3 (`source_quote` schema field + grounding check) was ranked third because B1's quote-into-analysis is its lite form. Decide with data.

- [ ] **Step 1: Compute the verbatim-grounding rate of stated rates from the B2 dump**

(The B2 dump has `products_rates` + `chunk_snippets` from Task 2 Step 5.)

```bash
python -c "
import json, re
rows=[json.loads(l) for l in open('evals/_out_clean_indepjudge_twostep.jsonl',encoding='utf-8')]
total=grounded=0
for r in rows:
    chunks=' '.join(r.get('chunk_snippets') or []).lower()
    for p in (r.get('products_rates') or []):
        rate=(p.get('rate') or '').strip().lower()
        if not rate: continue
        total+=1
        nums=re.findall(r'\d+\.?\d*', rate)
        if rate in chunks or (nums and all(n in chunks for n in nums)): grounded+=1
print(f'rates stated: {total}  verbatim/number-grounded in retrieved chunks: {grounded} ({100*grounded/max(total,1):.0f}%)')
"
```

- [ ] **Step 2: Decide**

- Grounding ≥ ~80% → **B3 redundant, close it**: edit the Phase B3 section of `docs/superpowers/plans/2026-06-12-answer-quality-next-lever.md` status note to "CLOSED — B1 already grounds rates (measured X%)".
- Grounding < ~80% → B3 stays a live candidate; its measured gap (the ungrounded %) goes in the findings doc as the expected headroom.

- [ ] **Step 3: Update PROGRESS.md and commit**

Add the session's outcome to the PROGRESS.md top section (new `▶` block, same format as "PHASE A HONEST BASELINE + B1"): rice bucket counts, B2 verdict + numbers, B3 decision, and the explicit NEXT. Update the "Last updated" banner line.

```bash
git add PROGRESS.md docs/superpowers/plans/2026-06-12-answer-quality-next-lever.md
git commit -m "docs(progress): rice diagnosis + B2 format-tax verdict + B3 decision"
git push origin main
```

(Evals/docs-only push — does not trigger the HF backend deploy Action.)

---

## Self-review notes

- All four tasks produce standalone value; Tasks 2–4 are skippable if Task 1's `TRUE_RETRIEVAL` stop-condition fires (it won't, per the n=40 audit, but the gate is there).
- The two-step wrapper deliberately does NOT touch `backend/` — productionizing is explicitly a separate plan in Task 3 Step 4.
- `_TwoStepRunnable.ainvoke` returns `AdvisoryDraft` (same type the real runnable returns), so `rag._postprocess_async` (including the B1 `analysis` strip) runs unchanged.
- Repair formatter is Groq 8b json_mode = $0; only the 40 DeepInfra generations + 80 Gemini judge calls cost money (~$0.05–0.10), and that run is OK-gated in Task 3 Step 1.
