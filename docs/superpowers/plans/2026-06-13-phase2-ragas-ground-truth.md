# Phase 2 — RAGAS Synthetic Ground-Truth + Human-Validated Answer Keys

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-gold-chunk correctness grading with **multi-reference answer-key grading**, so the correctness headline measures the answer (not which one chunk the model happened to match). Produces `evals/ground_truth/answer_keys.jsonl` — one human-validated reference answer per eval query — plus an answer-key correctness judge and RAGAS `answer_correctness` wired in.

**Architecture:** Eval-only. A new package `evals/ground_truth/` with pure helpers (synthesis prompt-builder, answer-key store, answer-key judge) + cost-gated LLM steps (synthesis, re-measure). The judge compares an advisory answer to a reference answer (credits any correct answer regardless of source chunk) — that is the fix for the single-gold artifact the rice curation surfaced (rice corr 10% / faith 86%; 62% of rice = `corr=0/faith=1.0`). Human-validation of a subset is the circularity guard: an LLM writes the ground truth, so a human must sign off before any of these numbers go in NIW/arXiv. Touches no `backend/`, `frontend/`, or retrieval pipeline.

**Tech Stack:** Python 3.13, pytest, RAGAS (already in repo, `evals/ragas_eval.py`), Gemini 2.5-flash judge (already wired). No new dependencies.

---

## Handoff (read first — built in a FRESH session)

- **Branch:** `feat/phase2-ragas-ground-truth` (this plan committed here, NOT `main`). `git switch feat/phase2-ragas-ground-truth` before starting. Eval-only → push triggers **no** HF/Vercel deploy (deploy Actions watch `backend/**` / `frontend/`).
- **Why this exists:** the rice-gold-curation re-measure (2026-06-13, merged `ef830ac`) proved rice low-corr is a **single-gold measurement artifact**, not a pipeline failure — the pipeline produces *grounded* answers (rice faith 86%) that score `corr=0` only because they don't match the one gold chunk. Curating which chunk is gold can't fix that (it traded a TOC-artifact for a keyword-mismatch-artifact). The real fix is grading against a **reference answer** (any correct answer scores correct), which is what this plan builds. See `PROGRESS.md` → "RESUME HERE" + `memory/project_rice_gold_curation.md`.
- **The honesty crux:** an LLM synthesizes the reference answers from the gold chunks → LLM-grades-LLM is circular (the same trap that invalidated MRR 0.65, `memory/project_eval_contamination.md`). **Mitigation is mandatory, not optional:** (1) synthesize from the gold chunk text only (grounded, not free-recall), (2) a human validates a sampled subset (Task 5 gate) before the numbers are reported, (3) the synthesis model (Gemini 2.5-flash) is distinct from the generation model under test (DeepInfra 70B / Claude). No correctness number from this plan is NIW/arXiv-quotable until the Task 5 human gate is signed off.
- **Cost map:** Tasks 1–4, 6 (pure helpers + tests) = **$0**. **Task 5a (synthesis)** spends Gemini-2.5-flash tokens (~198 grounded summary calls — cheap, but non-zero → **STOP for Taiwo OK**). **Task 7 (re-measure)** spends a gen re-run + RAGAS matrix (same per-run cost as prior arms → **STOP for Taiwo OK**). Taiwo is cost-averse (`memory/feedback_avoid_token_cost.md`).
- **Task 5b is the human-in-the-loop gate** — surface the validation sample to Taiwo, don't rubber-stamp synthetic answers.
- **Run all commands from the repo root.** Tests: `python -m pytest evals/ground_truth/...`. `.env` lives at repo ROOT.
- **Inputs present:** `evals/eval_set_v2_clean.jsonl` (198 rows, canonical), `evals/ragas_eval.py` (4-metric matrix), `evals/answer_eval_full.py` (gen harness, `--provider`/`--judge-provider`). Schema of the clean set: `{query, chunk_id, chunk_text, document_title, namespace}`.
- **Definition of done for the build session:** Tasks 1–4 + 6 implemented, committed per-task, full pytest green ($0); `evals/ground_truth/` package + answer-key judge + RAGAS `answer_correctness` wiring in place; Task 5 (synthesis + human validation) and Task 7 (re-measure) left pending Taiwo's cost OK. Once run, results → `PROGRESS.md`.

---

## File Structure

- **Create** `evals/ground_truth/__init__.py` — empty package marker.
- **Create** `evals/ground_truth/answer_keys.py` — the answer-key store + synthesis prompt-builder: `load_gold_by_query`, `build_synthesis_prompt`, `parse_answer_key`, `load_answer_keys`, `write_answer_keys`, `validation_sample`. All pure (no LLM/network).
- **Create** `evals/ground_truth/synth.py` — `main()` that runs the cost-gated Gemini synthesis over the gold chunks and writes `answer_keys.jsonl`. The ONLY LLM code in the build; cost-gated `--confirm-cost`.
- **Create** `evals/ground_truth/answerkey_judge.py` — `judge_against_answer_key(answer, reference_answer)` → `(score, rationale)`; pure prompt-builder `build_judge_prompt` + a thin Gemini call. `--grade-mode answerkey` consumer lives in answer_eval_full (Task 6).
- **Create** `evals/ground_truth/test_answer_keys.py` + `test_answerkey_judge.py` — pytest for every pure helper, seeded in-memory fixtures, no file/network dependency.
- **Create (generated, Task 5)** `evals/ground_truth/answer_keys.jsonl` — `{query, namespace, reference_answer, source_chunk_ids, validated}` per query.
- **Create (Task 5)** `docs/superpowers/findings/2026-06-13-phase2-answer-key-validation.md` — the human-review sample + sign-off.
- **Modify** `evals/ragas_eval.py` — add `AnswerCorrectness` (uses `reference`) behind a `--with-answer-key` flag that loads `answer_keys.jsonl` and sets `SingleTurnSample.reference`.
- **Modify** `evals/answer_eval_full.py` — add `--grade-mode {gold,answerkey}` (default `gold` = unchanged); `answerkey` swaps the correctness judge to `answerkey_judge` keyed on `answer_keys.jsonl`.

> **Originals preserved:** `evals/eval_set_v2_clean.jsonl`, `evals/eval_set_v2_clean_rice.jsonl`, `evals/ragas_eval.py`'s existing 4 metrics, and the default `--grade-mode gold` path are READ-ONLY in behavior — the new path is additive and opt-in.

---

## Task 1: Package + gold loader + synthesis prompt-builder

**Files:**
- Create: `evals/ground_truth/__init__.py`, `evals/ground_truth/answer_keys.py`
- Test: `evals/ground_truth/test_answer_keys.py`

- [ ] **Step 1: Write the failing test**

Create `evals/ground_truth/test_answer_keys.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from answer_keys import load_gold_by_query, build_synthesis_prompt


def test_load_gold_by_query_groups_multi_chunk():
    rows = [
        {"query": "q1", "namespace": "rice", "chunk_id": "a",
         "chunk_text": "Apply 90 lb N per acre.", "document_title": "rice guide"},
        {"query": "q1", "namespace": "rice", "chunk_id": "b",
         "chunk_text": "Split the nitrogen application.", "document_title": "rice guide"},
        {"query": "q2", "namespace": "soybeans", "chunk_id": "c",
         "chunk_text": "Plant in May.", "document_title": "soy guide"},
    ]
    by_q = load_gold_by_query(rows)
    assert set(by_q) == {"q1", "q2"}
    assert by_q["q1"]["namespace"] == "rice"
    assert [c["chunk_id"] for c in by_q["q1"]["chunks"]] == ["a", "b"]
    assert by_q["q2"]["chunks"][0]["chunk_text"] == "Plant in May."


def test_build_synthesis_prompt_grounds_in_chunks_only():
    entry = {"namespace": "rice", "chunks": [
        {"chunk_id": "a", "chunk_text": "Apply 90 lb N per acre."},
    ]}
    prompt = build_synthesis_prompt("how much nitrogen for rice", entry)
    # the grounding rule + the chunk text must both appear; no free recall
    assert "90 lb N per acre" in prompt
    assert "how much nitrogen for rice" in prompt
    assert "only" in prompt.lower()  # "use ONLY the passages" grounding instruction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/ground_truth/test_answer_keys.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'answer_keys'`.

- [ ] **Step 3: Create the package + helpers**

Create `evals/ground_truth/__init__.py` (empty file).

Create `evals/ground_truth/answer_keys.py`:

```python
"""OFFLINE answer-key store + synthesis/judge prompt-builders (eval-only).

Builds human-validated reference answers so correctness can be graded against
"any correct answer" instead of a single gold chunk. Fixes the single-gold
measurement artifact the rice curation surfaced (rice corr 10% / faith 86%).

NEVER imported by backend/rag.py or the request path.
"""
import json
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
CLEAN_SET = Path(__file__).parent.parent / "eval_set_v2_clean.jsonl"
ANSWER_KEYS = Path(__file__).parent / "answer_keys.jsonl"


def load_gold_by_query(rows: list[dict]) -> "OrderedDict[str, dict]":
    """Group gold rows by query -> {namespace, chunks:[{chunk_id, chunk_text}]}.

    Order preserved (first-seen). Multiple gold chunks per query are kept so
    synthesis can ground the reference answer in all of them.
    """
    by_q: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        q = r["query"]
        entry = by_q.setdefault(q, {"namespace": r.get("namespace"), "chunks": []})
        entry["chunks"].append(
            {"chunk_id": r.get("chunk_id"), "chunk_text": r.get("chunk_text", "")}
        )
    return by_q


def build_synthesis_prompt(query: str, entry: dict) -> str:
    """Prompt to synthesize a grounded reference answer from the gold chunks ONLY.

    Grounded (not free recall): the model may use only the provided passages, so
    a Gemini-distinct-from-generator judge does not leak outside knowledge.
    """
    passages = "\n\n".join(
        f"[chunk {i+1}] {c['chunk_text']}" for i, c in enumerate(entry["chunks"])
    )
    return (
        "You are building an answer key for an agricultural-advisory eval.\n"
        "Write the correct, concise reference answer to the farmer's question "
        "using ONLY the facts in the passages below. Do not add information not "
        "present in the passages. If the passages do not answer the question, "
        "reply exactly: INSUFFICIENT.\n\n"
        f"QUESTION: {query}\n\n"
        f"PASSAGES:\n{passages}\n\n"
        "REFERENCE ANSWER:"
    )


def parse_answer_key(query: str, namespace: str, source_chunk_ids: list[str],
                     raw_answer: str) -> dict | None:
    """Normalize one synthesized answer into an answer-key record.

    Returns None for an INSUFFICIENT / empty synthesis (those queries get no key
    and are skipped by the answerkey grader). validated defaults False.
    """
    text = (raw_answer or "").strip()
    if not text or text.upper().startswith("INSUFFICIENT"):
        return None
    return {
        "query": query,
        "namespace": namespace,
        "reference_answer": text,
        "source_chunk_ids": source_chunk_ids,
        "validated": False,
    }


def load_answer_keys(path=ANSWER_KEYS) -> dict:
    """Load answer_keys.jsonl into {query -> record}."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                out[rec["query"]] = rec
    return out


def write_answer_keys(records: list[dict], path=ANSWER_KEYS) -> None:
    """Write answer-key records (one JSON object per line)."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def validation_sample(records: list[dict], per_namespace: int = 5, seed: int = 7) -> list[dict]:
    """Deterministic stratified sample for the Task 5 human gate: up to
    per_namespace records per namespace."""
    import random
    by_ns: "OrderedDict[str, list]" = OrderedDict()
    for r in records:
        by_ns.setdefault(r.get("namespace"), []).append(r)
    rng = random.Random(seed)
    out = []
    for ns, recs in by_ns.items():
        picks = recs if len(recs) <= per_namespace else rng.sample(recs, per_namespace)
        out.extend(picks)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest evals/ground_truth/test_answer_keys.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ground_truth/__init__.py evals/ground_truth/answer_keys.py evals/ground_truth/test_answer_keys.py
git commit -m "feat(evals): answer-key store + grounded synthesis prompt (Phase 2 Task 1)"
```

---

## Task 2: `parse_answer_key` + store round-trip + validation sample

**Files:**
- Test: `evals/ground_truth/test_answer_keys.py` (append)

- [ ] **Step 1: Append the failing tests**

```python
from answer_keys import (parse_answer_key, write_answer_keys, load_answer_keys,
                         validation_sample)


def test_parse_answer_key_drops_insufficient_and_marks_unvalidated():
    ok = parse_answer_key("q", "rice", ["a"], "Apply 90 lb N per acre, split.")
    assert ok["reference_answer"].startswith("Apply 90")
    assert ok["validated"] is False
    assert ok["source_chunk_ids"] == ["a"]
    assert parse_answer_key("q", "rice", ["a"], "INSUFFICIENT") is None
    assert parse_answer_key("q", "rice", ["a"], "   ") is None


def test_answer_keys_round_trip(tmp_path):
    recs = [
        {"query": "q1", "namespace": "rice", "reference_answer": "A",
         "source_chunk_ids": ["a"], "validated": False},
        {"query": "q2", "namespace": "soybeans", "reference_answer": "B",
         "source_chunk_ids": ["b"], "validated": True},
    ]
    p = tmp_path / "ak.jsonl"
    write_answer_keys(recs, p)
    loaded = load_answer_keys(p)
    assert set(loaded) == {"q1", "q2"}
    assert loaded["q2"]["validated"] is True


def test_validation_sample_is_stratified_and_deterministic():
    recs = ([{"query": f"r{i}", "namespace": "rice", "reference_answer": "x",
              "source_chunk_ids": [], "validated": False} for i in range(20)]
            + [{"query": f"s{i}", "namespace": "soybeans", "reference_answer": "y",
                "source_chunk_ids": [], "validated": False} for i in range(3)])
    s1 = validation_sample(recs, per_namespace=5, seed=7)
    s2 = validation_sample(recs, per_namespace=5, seed=7)
    assert [r["query"] for r in s1] == [r["query"] for r in s2]  # deterministic
    rice = [r for r in s1 if r["namespace"] == "rice"]
    soy = [r for r in s1 if r["namespace"] == "soybeans"]
    assert len(rice) == 5 and len(soy) == 3  # capped per namespace; soy has only 3
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest evals/ground_truth/test_answer_keys.py -v`
Expected: PASS (5 passed) — all helpers were implemented in Task 1; these lock their contracts.

- [ ] **Step 3: Commit**

```bash
git add evals/ground_truth/test_answer_keys.py
git commit -m "test(evals): lock answer-key parse/store/sample contracts (Phase 2 Task 2)"
```

---

## Task 3: Answer-key correctness judge (prompt-builder + parser)

**Files:**
- Create: `evals/ground_truth/answerkey_judge.py`
- Test: `evals/ground_truth/test_answerkey_judge.py`

The judge scores the advisory answer against the reference answer — crediting any answer that conveys the same correct agronomic content, regardless of which corpus chunk it came from. This is the multi-reference fix. The Gemini call is isolated behind `judge_against_answer_key`; the pure parts (`build_judge_prompt`, `_parse_judge_score`) are unit-tested.

- [ ] **Step 1: Write the failing test**

Create `evals/ground_truth/test_answerkey_judge.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from answerkey_judge import build_judge_prompt, _parse_judge_score


def test_build_judge_prompt_includes_both_answers():
    p = build_judge_prompt(
        query="how much nitrogen for rice",
        answer="Use about 90 lb of nitrogen per acre, split into two.",
        reference_answer="Apply 90 lb N/acre, split application.",
    )
    assert "90 lb of nitrogen" in p           # candidate answer
    assert "Apply 90 lb N/acre" in p          # reference answer
    assert "how much nitrogen for rice" in p  # query
    # must instruct source-independent grading
    assert "regardless" in p.lower() or "any correct" in p.lower()


def test_parse_judge_score_reads_verdict_line():
    assert _parse_judge_score("Reasoning: matches.\nSCORE: 1.0") == 1.0
    assert _parse_judge_score("partial\nSCORE: 0.5") == 0.5
    assert _parse_judge_score("SCORE: 0") == 0.0
    # robust to stray text / missing -> None
    assert _parse_judge_score("no verdict here") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/ground_truth/test_answerkey_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'answerkey_judge'`.

- [ ] **Step 3: Implement the judge**

Create `evals/ground_truth/answerkey_judge.py`:

```python
"""OFFLINE answer-key correctness judge (eval-only).

Grades an advisory answer against a human-validated reference answer, crediting
any answer that conveys the correct agronomic content regardless of which corpus
chunk it came from. This is the multi-reference fix for the single-gold artifact.

NEVER imported by backend/rag.py or the request path.
"""
import os
import re
from pathlib import Path

_SCORE_RE = re.compile(r"SCORE:\s*([01](?:\.\d+)?)", re.IGNORECASE)


def build_judge_prompt(query: str, answer: str, reference_answer: str) -> str:
    return (
        "You are grading an agricultural advisory answer for correctness.\n"
        "Compare the CANDIDATE answer to the REFERENCE answer. Credit the "
        "candidate if it conveys the same correct, safe agronomic guidance for "
        "the question — regardless of wording, source, or extra detail. A "
        "different-but-correct answer is still correct. Penalize wrong rates, "
        "wrong products, unsafe advice, or failure to answer.\n\n"
        f"QUESTION: {query}\n\n"
        f"REFERENCE ANSWER: {reference_answer}\n\n"
        f"CANDIDATE ANSWER: {answer}\n\n"
        "Reply with one line of reasoning, then a final line exactly:\n"
        "SCORE: <1.0 = correct | 0.5 = partially correct | 0.0 = incorrect>"
    )


def _parse_judge_score(raw: str):
    m = _SCORE_RE.search(raw or "")
    return float(m.group(1)) if m else None


_judge = None


def _get_judge():
    """Independent Gemini 2.5-flash judge (distinct from the generation model)."""
    global _judge
    if _judge is None:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        _judge = ChatGoogleGenerativeAI(
            model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0,
        )
    return _judge


def judge_against_answer_key(query: str, answer: str, reference_answer: str):
    """Return (score in {0.0,0.5,1.0} or None, raw_rationale). Spends Gemini tokens."""
    prompt = build_judge_prompt(query, answer, reference_answer)
    raw = _get_judge().invoke(prompt).content
    return _parse_judge_score(raw), raw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest evals/ground_truth/test_answerkey_judge.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ground_truth/answerkey_judge.py evals/ground_truth/test_answerkey_judge.py
git commit -m "feat(evals): answer-key correctness judge (Phase 2 Task 3)"
```

---

## Task 4: Synthesis runner (`synth.py`, cost-gated, no run yet)

**Files:**
- Create: `evals/ground_truth/synth.py`
- Test: `evals/ground_truth/test_answer_keys.py` (append — test the pure assembly, not the LLM)

`synth.py` wires the Task 1 helpers into a cost-gated run: load the clean set, group by query, build the grounded prompt per query, call Gemini, parse to an answer-key record, write `answer_keys.jsonl`. The build session implements and unit-tests the assembly but does NOT run it (Task 5 is the cost gate).

- [ ] **Step 1: Append the failing test (pure assembly via injected fake LLM)**

```python
from answer_keys import load_gold_by_query


def test_synth_build_records_uses_injected_llm(monkeypatch):
    import synth
    rows = [
        {"query": "q1", "namespace": "rice", "chunk_id": "a",
         "chunk_text": "Apply 90 lb N per acre.", "document_title": "g"},
        {"query": "q2", "namespace": "rice", "chunk_id": "b",
         "chunk_text": "no answer here", "document_title": "g"},
    ]
    # fake LLM: answers q1, says INSUFFICIENT for q2
    def fake_call(prompt):
        return "Apply 90 lb N/acre." if "90 lb N" in prompt else "INSUFFICIENT"

    records = synth.build_records(load_gold_by_query(rows), call_llm=fake_call)
    # q2 dropped (INSUFFICIENT); q1 kept and grounded
    assert [r["query"] for r in records] == ["q1"]
    assert records[0]["reference_answer"] == "Apply 90 lb N/acre."
    assert records[0]["source_chunk_ids"] == ["a"]
    assert records[0]["validated"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/ground_truth/test_answer_keys.py -k synth -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'synth'`.

- [ ] **Step 3: Implement `synth.py`**

Create `evals/ground_truth/synth.py`:

```python
"""OFFLINE answer-key synthesis runner (cost-gated — spends Gemini tokens).

Generates one grounded reference answer per eval query from its gold chunk(s).
Cost-gated: prints an estimate unless --confirm-cost is passed. The pure assembly
(build_records) is injected with the LLM call so it is unit-tested without spend.

NEVER imported by backend/rag.py or the request path.
"""
import argparse
import json
from pathlib import Path

from answer_keys import (load_gold_by_query, build_synthesis_prompt,
                         parse_answer_key, write_answer_keys, CLEAN_SET, ANSWER_KEYS)


def build_records(by_query: dict, call_llm) -> list[dict]:
    """Synthesize answer-key records. `call_llm(prompt)->str` is injected so this
    is pure/testable. Drops INSUFFICIENT/empty syntheses (parse_answer_key None)."""
    records = []
    for query, entry in by_query.items():
        raw = call_llm(build_synthesis_prompt(query, entry))
        rec = parse_answer_key(
            query, entry["namespace"],
            [c["chunk_id"] for c in entry["chunks"]],
            raw,
        )
        if rec is not None:
            records.append(rec)
    return records


def _gemini_call():
    """Build the real Gemini 2.5-flash synthesis call (distinct from generator)."""
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.environ["GOOGLE_API_KEY"], temperature=0,
    )
    return lambda prompt: llm.invoke(prompt).content


_COST_NOTE = """\
COST GATE — synthesis spends Gemini-2.5-flash tokens (~one grounded summary call
per eval query; ~198 calls for the clean set — cheap but non-zero).
Re-run with --confirm-cost to proceed."""


def main():
    ap = argparse.ArgumentParser(description="Synthesize answer keys (cost-gated).")
    ap.add_argument("--eval-set", type=Path, default=CLEAN_SET)
    ap.add_argument("--out", type=Path, default=ANSWER_KEYS)
    ap.add_argument("--confirm-cost", action="store_true")
    args = ap.parse_args()
    if not args.confirm_cost:
        print(_COST_NOTE)
        raise SystemExit(0)

    rows = [json.loads(l) for l in open(args.eval_set, encoding="utf-8") if l.strip()]
    by_q = load_gold_by_query(rows)
    records = build_records(by_q, call_llm=_gemini_call())
    write_answer_keys(records, args.out)
    n_drop = len(by_q) - len(records)
    print(f"answer keys: {len(records)} written, {n_drop} INSUFFICIENT/dropped -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/ground_truth/ -v`
Expected: all PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ground_truth/synth.py evals/ground_truth/test_answer_keys.py
git commit -m "feat(evals): cost-gated answer-key synthesis runner (Phase 2 Task 4)"
```

---

## Task 5: SYNTHESIS + HUMAN VALIDATION GATE (cost-gated — STOP for OK)

**This task spends Gemini tokens (5a) and requires Taiwo's review (5b). Get explicit OK before 5a.**

- [ ] **Step 1 (5a): State the cost estimate and get Taiwo's OK, then synthesize**

~198 Gemini-2.5-flash grounded summary calls (cheap, single-digit cents, but non-zero). On OK:
```bash
python evals/ground_truth/synth.py --confirm-cost
```
Expected: `answer keys: ~190 written, ~8 INSUFFICIENT/dropped -> .../answer_keys.jsonl`.

- [ ] **Step 2 (5b): Generate the validation sample + present it to Taiwo**

```bash
python -c "import sys; sys.path.insert(0,'evals/ground_truth'); import json; from answer_keys import load_answer_keys, validation_sample; recs=list(load_answer_keys().values()); s=validation_sample(recs); open('docs/superpowers/findings/2026-06-13-phase2-answer-key-validation.md','w',encoding='utf-8').write('# Phase 2 Answer-Key Validation\n\nReview each. Mark CORRECT/EDIT/DROP. Sign-off gates any NIW/arXiv use.\n\n' + '\n'.join(f'## {r[\"namespace\"]}: {r[\"query\"][:80]}\n- ref: {r[\"reference_answer\"]}\n- verdict: \n' for r in s)); print('validation doc written:', len(s), 'items')"
```
> **This is the circularity guard.** Surface the doc to Taiwo. For each item Taiwo marks CORRECT → set `validated: true` in `answer_keys.jsonl`; EDIT → fix `reference_answer` + set `validated: true`; DROP → remove the record. Do NOT mass-flip `validated` without the human pass.

- [ ] **Step 3: Apply Taiwo's verdicts to `answer_keys.jsonl` + record sign-off in the validation doc**

- [ ] **Step 4: Commit**

```bash
git add evals/ground_truth/answer_keys.jsonl docs/superpowers/findings/2026-06-13-phase2-answer-key-validation.md
git commit -m "chore(evals): synthesize + human-validate answer keys (Phase 2 Task 5)"
```

---

## Task 6: Wire answer keys into the eval harness + RAGAS

**Files:**
- Modify: `evals/answer_eval_full.py` (add `--grade-mode {gold,answerkey}`)
- Modify: `evals/ragas_eval.py` (add `AnswerCorrectness` behind `--with-answer-key`)
- Test: `evals/ground_truth/test_answerkey_judge.py` (append a wiring unit test)

- [ ] **Step 1: Write the failing test (answerkey grade selection is pure given an injected judge)**

Append to `evals/ground_truth/test_answerkey_judge.py`:

```python
from answerkey_judge import grade_with_answer_key


def test_grade_with_answer_key_skips_unkeyed_and_scores_keyed():
    keys = {"q1": {"reference_answer": "Apply 90 lb N/acre.", "validated": True}}
    calls = []
    def fake_judge(query, answer, ref):
        calls.append(query)
        return (1.0, "ok")
    # q1 keyed+validated -> judged; q2 has no key -> None (skipped)
    assert grade_with_answer_key("q1", "use ~90 lb N", keys, judge=fake_judge) == 1.0
    assert grade_with_answer_key("q2", "whatever", keys, judge=fake_judge) is None
    # unvalidated key is not used (circularity guard)
    keys2 = {"q3": {"reference_answer": "x", "validated": False}}
    assert grade_with_answer_key("q3", "x", keys2, judge=fake_judge) is None
    assert calls == ["q1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/ground_truth/test_answerkey_judge.py -k grade_with_answer_key -v`
Expected: FAIL — `ImportError: cannot import name 'grade_with_answer_key'`.

- [ ] **Step 3: Add `grade_with_answer_key` to `answerkey_judge.py`**

```python
def grade_with_answer_key(query, answer, answer_keys, judge=judge_against_answer_key):
    """Grade `answer` for `query` against a VALIDATED answer key.

    Returns the score, or None when there is no key for the query or the key is
    not human-validated (circularity guard — unvalidated keys never score).
    """
    key = answer_keys.get(query)
    if not key or not key.get("validated"):
        return None
    score, _ = judge(query, answer, key["reference_answer"])
    return score
```

- [ ] **Step 4: Wire `--grade-mode answerkey` into `answer_eval_full.py`**

In `evals/answer_eval_full.py` `main()`, after the argument parser, add:
```python
    ap.add_argument("--grade-mode", choices=["gold", "answerkey"], default="gold",
                    help="gold=single gold-chunk judge (default); "
                         "answerkey=multi-reference judge vs validated answer keys")
```
Load the keys when selected (near the dump/eval setup):
```python
    _answer_keys = {}
    if args.grade_mode == "answerkey":
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent / "ground_truth"))
        from answer_keys import load_answer_keys
        _answer_keys = load_answer_keys()
```
In `evaluate(item)` (or where `correctness` is computed), when `--grade-mode answerkey` and a validated key exists, replace the gold-chunk correctness with `grade_with_answer_key(...)`; when it returns `None`, fall back to the existing gold judge so coverage never drops. Keep the default `gold` path byte-for-byte unchanged. (Thread `grade_mode`/`_answer_keys` through `evaluate` via a module global the same way `_judge` is threaded.)

- [ ] **Step 5: Add `AnswerCorrectness` to `ragas_eval.py` behind `--with-answer-key`**

In `evals/ragas_eval.py`:
- `build_samples` gains an optional `answer_key_map` param; when provided, set `SingleTurnSample(..., reference=answer_key_map.get(r["query"]))`.
- `run()` adds `AnswerCorrectness()` (from `ragas.metrics`) to `metrics` only when `--with-answer-key` is passed and the key is validated; load keys via `ground_truth.answer_keys.load_answer_keys()` filtered to `validated`.
- New CLI flag `--with-answer-key` (off by default → existing 4-metric matrix unchanged).

- [ ] **Step 6: Run the full suite (still green; existing paths unchanged)**

Run: `python -m pytest evals/ground_truth/ -v`
Expected: all PASS (7 passed). Also confirm the default `gold` path is untouched: `python -m pytest evals/test_answer_eval*.py -v` (if present) stays green.

- [ ] **Step 7: Commit**

```bash
git add evals/answer_eval_full.py evals/ragas_eval.py evals/ground_truth/answerkey_judge.py evals/ground_truth/test_answerkey_judge.py
git commit -m "feat(evals): answerkey grade-mode + RAGAS answer_correctness wiring (Phase 2 Task 6)"
```

---

## Task 7: Re-measure on answer keys (MANUAL, cost-gated — STOP for OK)

**This task spends tokens. Get explicit Taiwo OK before running.**

- [ ] **Step 1: State the cost estimate and get Taiwo's OK**

A gen re-run n=40 (DeepInfra 70B, B1 on) graded with `--grade-mode answerkey` (independent Gemini judge) gives the new **multi-reference** corr headline — the honest rice corr the single-gold number couldn't produce. Optional RAGAS `--with-answer-key` adds `answer_correctness`. Same per-run cost as prior arms.

- [ ] **Step 2: Headline re-run (after OK)**

```bash
python evals/answer_eval_full.py --provider deepinfra --judge-provider gemini \
  --grade-mode answerkey --eval-set evals/eval_set_v2_clean.jsonl --sample 40 --seed 7 \
  --dump evals/_capture_answerkey.jsonl
```
Expected: rice corr materially above the single-gold 10% if the artifact diagnosis holds (faith should be ~unchanged — it never used gold). Record the per-namespace row.

- [ ] **Step 3: (Optional) RAGAS answer_correctness (after OK)**

```bash
python evals/ragas_eval.py --dump evals/_capture_answerkey.jsonl \
  --with-answer-key --confirm-cost
```

- [ ] **Step 4: Record results + gitignore artifacts**

Add `evals/_capture_answerkey.jsonl` to `.gitignore` (eval-artifacts block — `evals/_capture_*.jsonl` already covers it). Update `PROGRESS.md` with the multi-reference corr headline + whether rice corr rose (confirming the single-gold artifact). Then:
```bash
git add PROGRESS.md
git commit -m "docs(progress): Phase 2 multi-reference correctness results"
```

---

## Self-Review (completed)

- **Spec/goal coverage:** multi-reference grading → Task 3 judge + Task 6 `grade_with_answer_key`/`--grade-mode answerkey`. Synthetic ground truth → Task 1 prompt + Task 4 runner + Task 5a. Human-validation circularity guard → Task 5b gate + `validated` flag enforced in `grade_with_answer_key` and the RAGAS `--with-answer-key` filter. RAGAS `answer_correctness` (the un-provisioned cell) → Task 6 Step 5. Cost gates → Task 5a / Task 7 (`--confirm-cost`, STOP for OK). Eval-only / no pipeline change → no task touches `backend/`/`frontend/`.
- **Placeholder scan:** every pure-helper step has complete code + a failing test + expected output; the LLM steps (5a, 7) are deliberately cost-gated manual runs with exact commands. Task 6 Step 4 describes the threading rather than pasting the whole 400-line harness — it names the exact arg, load site, and the keep-default-unchanged constraint.
- **Type consistency:** `load_gold_by_query(rows)->OrderedDict[query->{namespace,chunks}]` (T1) feeds `build_synthesis_prompt(query,entry)` (T1) and `build_records(by_query, call_llm)` (T4). `parse_answer_key(...)->record|None` (T1) feeds `build_records` + `write_answer_keys` (T1). `load_answer_keys()->{query->record}` (T1) feeds `grade_with_answer_key(query,answer,keys,judge)->score|None` (T6) and the RAGAS `answer_key_map`. `build_judge_prompt`/`_parse_judge_score` (T3) underlie `judge_against_answer_key->(score,raw)` (T3). `validated` flag is the single circularity-guard gate, enforced in T6 both places. Consistent.
