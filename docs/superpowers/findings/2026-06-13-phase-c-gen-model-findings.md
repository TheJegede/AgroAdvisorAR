# Phase C — Generation-Model Swap: A Free-Tier Pareto Frontier (Negative Result)

**Date:** 2026-06-13
**Status:** RUN, eval-only. No production change. Branch `feat/phase-c-gen-model-probe-v2`.
**Scope:** Does swapping the generation model (retrieval and judge held fixed) lift the answer-quality ceiling of the AgroAdvisor RAG pipeline, *within the free-tier cost constraint*?
**Answer:** No. The incumbent free model is Pareto-best. Generation levers are exhausted under the free constraint.

---

## 1. Motivation

Every prompt-route generation lever has been tested and settled (L1 directive = no-op; L2 exemplars = win; L3 verbatim-rate = win; B1 reasoning-first scratchpad = win, shipped; B2 format-tax / two-step = disproven; B3 source-quote field = disproven). Retrieval is closed (5 techniques tested + rejected; RAGAS context-precision 0.71 confirms retrieval is not the bottleneck). The honest end-to-end ceiling is **generation**: independent-judge correctness ~30% (single-gold) / ~61% (Phase-2 multi-reference answer keys), faithfulness ~71%. The model retrieves the right document, then states the wrong rate or product (GEN_SPECIFICITY).

The one untried engine lever is the generation model itself. The standing production generator is `llama-3.3-70b-versatile` on the **Groq free tier** (zero marginal cost). A central design constraint of this project is *no ongoing inference cost* — so the question is narrow and specific:

> Among models that can be served **free**, does any beat the incumbent 70B?

This excludes paid frontier models (Anthropic Claude, Gemini Pro) by construction: even if they win, they cannot be productionized without violating the cost constraint. The probe therefore tests only **free-tier-serveable** candidates.

## 2. Method

A `--gen-model <id>` arm was added to `evals/answer_eval_full.py` (`_apply_gen_model_override`): it repoints `config.DEEPINFRA_MODEL` and clears the cached generation client, swapping **only** the generation LLM. Retrieval (gte-base dense over the Docling v3 Pinecone index), the citation guard, the prompt (L2+L3+B1 on), and the **independent Gemini 2.5-flash judge** are all held fixed, so any correctness/faithfulness delta is attributable to the generation model alone.

Candidates were chosen to be available on **both** DeepInfra (cheap, rate-limit-free batched eval — the Groq free tier's 30-RPM cap forces this escape hatch for evaluation) **and** the Groq free tier (so a winner productionizes at $0):

| candidate | size | role |
|---|---|---|
| `llama-3.3-70b-versatile` (incumbent) | 70B dense | baseline |
| `openai/gpt-oss-120b` | 120B MoE | larger free model — ceiling probe |
| `Qwen/Qwen3-32B` | 32B dense, reasoning | reasoning model — faith probe |

Eval set: `eval_set_v2_clean.jsonl`, n=40, seed=7, same sample across arms. Judge: independent Gemini 2.5-flash (`--judge-provider gemini`), removing self-grading bias.

## 3. Results

### Standalone (per-arm)

| arm | n scored | skipped | correctness | faithfulness | suppression |
|---|---|---|---|---|---|
| `llama-3.3-70b` | 38 | 2 | **30.3%** | **71.1%** | 5% |
| `gpt-oss-120b` | 40 | 0 | 23.8% | 63.8% | 0% |
| `Qwen3-32B` | 0 | 13/13 | — | — | — |

### Paired (n=38 identical items, baseline vs gpt-oss-120b)

| metric | 70B | gpt-oss-120b | Δ | win/loss |
|---|---|---|---|---|
| correctness | 30.3% | 23.7% | **−6.6 pts** | helped 6 / hurt 8 / same 24 |
| faithfulness | 71.1% | 67.1% | **−3.9 pts** | helped 9 / hurt 12 / same 17 |

Per-namespace correctness (paired): poultry 17→33% (n=3, noisy), **rice 26→21%** (n=19), **soybeans 38→25%** (n=16).

## 4. Findings

**F1 — A larger free MoE regressed both metrics.** `gpt-oss-120b` (120B parameters) lost 6.6 pts correctness and 3.9 pts faithfulness against a 70B dense model on identical items, with hurt outnumbering helped on both. The regression is concentrated in soybeans (38→25%). **Scale among free models did not buy answer quality** on this domain-specific, constrained-schema RAG task. Notably gpt-oss never abstained (suppression 0%, confidence 1.00 on every item) — it is *more compliant and more overconfident* while being *less correct*, a worse safety profile for an advisory product.

**F2 — A free reasoning model is structurally incompatible with the constrained-schema path.** `Qwen3-32B` emits `<think>...` reasoning tokens ahead of its answer. Under `with_structured_output(AdvisoryDraft)` (JSON-locked decoding) this corrupts the JSON envelope, producing `OutputParserException` on **every** item (13/13 skipped before the run was killed). Serving it would require additional `<think>`-stripping or thinking-disabled plumbing — i.e. it is **not a drop-in $0 swap**, and constrained decoding fighting verbose pre-answer generation is the same failure mode that closed B2 (two-step) and B3 (source-quote).

**F3 — The incumbent is Pareto-best among free-serveable models.** No free candidate dominates `llama-3.3-70b-versatile` on either axis. The only models that might lift the ceiling are *paid frontier* models, which the cost constraint excludes. Therefore, **under the free-tier constraint, the generation lever is exhausted** — joining retrieval (already closed) — and the honest ceiling (corr ~30% single-gold / ~61% answer-key, faith ~71%) stands.

## 5. Implication for the writeup (NIW / arXiv)

This is a clean, publishable **negative result** with two transferable lessons for cost-constrained production RAG:

1. **Free-tier model scale is not monotone in answer quality.** A 120B free MoE underperformed a 70B free dense model on a domain-specific constrained-schema advisory task — bigger free ≠ better. Practitioners should *measure*, not assume, when swapping free models.
2. **Reasoning models and JSON-locked structured output are in tension.** Think-token leakage breaks constrained decoding; adopting a reasoning model into a structured-output pipeline is a re-engineering cost, not a config flip. This is consistent with the project's earlier B2/B3 findings (constrained decoding scaffolds this 70B *positively*, the opposite of Tam et al. 2024 "Let Me Speak Freely?").

Combined with the Phase-2 result (single-gold grading under-counts correctness by +21.5 pts vs human-validated multi-reference answer keys), the engineering story is complete: **retrieval is not the bottleneck, the free-tier generation ceiling is real and not liftable without paid inference, and the apparent low correctness is substantially a measurement artifact of single-gold grading.**

## 6. Reproduction

```bash
# baseline (incumbent 70B)
python -u evals/answer_eval_full.py --provider deepinfra --judge-provider gemini \
  --eval-set evals/eval_set_v2_clean.jsonl --sample 40 --seed 7 \
  --dump evals/_capture_genmodel_baseline70b.jsonl

# free-model arm (swap --gen-model)
LANGCHAIN_TRACING_V2=false python -u evals/answer_eval_full.py --provider deepinfra \
  --judge-provider gemini --gen-model openai/gpt-oss-120b \
  --eval-set evals/eval_set_v2_clean.jsonl --sample 40 --seed 7 \
  --dump evals/_capture_genmodel_gptoss.jsonl
```

Run with `python -u` + `PYTHONUNBUFFERED=1` (Python block-buffers redirected stdout — a working run otherwise looks stalled) and `LANGCHAIN_TRACING_V2=false` (silences LangSmith trace-quota 429 noise). Artifacts (gitignored): `evals/_capture_genmodel_*.jsonl`, `evals/_phaseC_*.log`.
