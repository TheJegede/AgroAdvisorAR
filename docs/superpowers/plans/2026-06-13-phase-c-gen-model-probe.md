# Phase C — Generation Model Swap (eval-only probe first, productionize gated)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how much a stronger generation model lifts the actual answer-quality ceiling (faithfulness + correctness), **eval-only**, without committing prod to an ongoing-cost model. Adds a `--gen-model` provider arm to `evals/answer_eval_full.py` that swaps ONLY the generation LLM (same retrieval, same independent Gemini judge), so the corr/faith delta is attributable to the model. Productionization is a separate, explicitly-gated follow-up that touches `backend/`.

**Architecture:** Eval-only for Tasks 1–3. The harness already pre-seeds `rag._deepinfra_llm` for the two-step arm; Phase C reuses that exact hook to pre-seed a Claude (or Gemini-pro) client as the generation LLM via `with_structured_output(AdvisoryDraft)`. Generation is the answer-quality ceiling (faith ~0.72 / 57–65% corr; prompt levers L1/L2/L3/B1/B2 EXHAUSTED) — this is the one remaining lever that moves the engine, not the ruler. **faith is readable today** (it doesn't use gold); **corr is only fully readable after Phase 2** (multi-reference answer keys) — so this probe leads with the faith delta and treats corr as directional until Phase 2 lands.

**Tech Stack:** Python 3.13, pytest, `langchain_anthropic` (ChatAnthropic) for Claude arms / existing `langchain_google_genai` for a Gemini-pro arm. The eval probe needs `ANTHROPIC_API_KEY` (Claude arm) in repo-root `.env`.

---

## Handoff (read first — built in a FRESH session)

- **Branch:** `feat/phase-c-gen-model-probe` (this plan committed here, NOT `main`). `git switch feat/phase-c-gen-model-probe` before starting. Tasks 1–3 are eval-only → push triggers **no** deploy. **Task 5 (productionize) DOES touch `backend/` → push to main auto-deploys to HF** — gated, do not run without explicit Taiwo OK.
- **Why this exists:** every prompt-route generation lever is exhausted (L1=NO-OP, L2=WIN, L3=WIN, B1=WIN, B2=DISPROVEN — `memory/project_l1_conditional_lever.md`) and retrieval is CLOSED. The honest ceiling is **generation**: RAGAS faith 0.72, eval faith 57–65%, the model retrieves the right doc then states the wrong rate/product (GEN_SPECIFICITY). The only untried engine-lever is a stronger generation model. See `PROGRESS.md` → "RESUME HERE".
- **The cost tension (read before recommending productionization):** prod generation today is `llama-3.3-70b-versatile` on **Groq free tier** (no budget). A frontier model = real per-query cost **forever**. Taiwo is cost-averse (`memory/feedback_avoid_token_cost.md`). So this plan's *primary deliverable is the eval-only measurement* — "what would a better model buy us" — and productionization (Task 5) is a separate decision Taiwo makes with the numbers in hand. Do not productionize as part of the probe.
- **Candidate models (current IDs/pricing, per the `claude-api` skill — verified 2026-06-13):** the harness is **model-agnostic** (`--gen-model <id>`). Probe candidates, cheapest-first for a cost-sensitive ag app:
  | model | id | $/1M in | $/1M out | role |
  |---|---|---|---|---|
  | Claude Haiku 4.5 | `claude-haiku-4-5` | $1.00 | $5.00 | cheapest frontier-family; test if it already beats 70B |
  | Claude Sonnet 4.6 | `claude-sonnet-4-6` | $3.00 | $15.00 | **realistic productionization candidate** (quality/cost balance) |
  | Claude Opus 4.8 | `claude-opus-4-8` | $5.00 | $25.00 | ceiling probe — how high can corr/faith go |
  | Gemini 2.5-flash/pro | (Google) | — | — | already in the stack (guard/judge); a same-vendor arm |
  Recommended sweep order: **Haiku 4.5 → Sonnet 4.6 → (optionally) Opus 4.8**, stopping once the faith lift vs cost is clear. The worked command below uses `claude-opus-4-8` (the skill default / ceiling arm); swap `--gen-model` for the cheaper arms. **Claude models 4.6+ reject `temperature`/`top_p`/`budget_tokens` and last-assistant-turn prefills, and need `thinking:{type:"adaptive"}` not a budget** — the harness must NOT pass sampling params to a Claude client (Task 2 Step 3 handles this).
- **Cost map:** Tasks 1–2, 4 (harness + tests) = **$0**. **Task 3 (probe runs)** spends generation tokens on the candidate model + Gemini judge per arm (n=40 each → STOP for Taiwo OK per arm; state the per-arm $ estimate from the table above). **Task 5 (productionize)** is gated separately AND incurs ongoing prod cost.
- **Run all commands from the repo root.** `.env` at repo ROOT. Tests: `python -m pytest evals/test_gen_model_probe.py`.
- **Definition of done for the build session:** Tasks 1–2 + 4 implemented, committed per-task, pytest green ($0); the `--gen-model` arm builds a Claude/Gemini gen client and pre-seeds it into `run_rag_query` without sampling-param 400s; default behavior (no `--gen-model`) byte-for-byte unchanged. Task 3 (probe) and Task 5 (productionize) left pending Taiwo's cost OK. Results → `PROGRESS.md`.

---

## File Structure

- **Create** `evals/gen_model_probe.py` — the gen-client builder: `build_gen_client(model_id)` returns a LangChain chat model with sampling params stripped for Claude-4.6+/Fable, ready for `.with_structured_output(AdvisoryDraft)`. Pure construction + a small `is_anthropic_model`/`strip_unsupported_params` helper set (unit-tested without network).
- **Create** `evals/test_gen_model_probe.py` — pytest for the pure helpers (model-family detection, param stripping, client class selection via injected factory). No network.
- **Modify** `evals/answer_eval_full.py` — add `--gen-model <id>`; when set, build the client via `gen_model_probe.build_gen_client` and pre-seed it as the generation LLM (same mechanism the `--two-step` arm uses to pre-seed `rag._deepinfra_llm`), with `config.LLM_PRIMARY` pointed at that slot. Default (unset) path unchanged.
- **(Task 5, gated, touches backend)** `backend/services/rag.py` + `backend/config.py` — add the chosen provider to the real provider chain behind an env flag (`LLM_PRIMARY=anthropic` + `ANTHROPIC_API_KEY`), fallback-safe to Groq.

> **Originals preserved:** the default `--provider deepinfra/groq/gemini/local` arms and the no-`--gen-model` path are READ-ONLY in behavior — the new arm is additive and opt-in.

---

## Task 1: Model-family detection + unsupported-param stripping

**Files:**
- Create: `evals/gen_model_probe.py`
- Test: `evals/test_gen_model_probe.py`

Claude 4.6+/Opus 4.7/4.8/Fable reject `temperature`/`top_p`/`top_k`/`budget_tokens` and need adaptive thinking — so the gen client for those models must be built without sampling params. This task is the pure logic that decides what to strip; Task 2 builds the actual client.

- [ ] **Step 1: Write the failing test**

Create `evals/test_gen_model_probe.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gen_model_probe import is_anthropic_model, sampling_unsupported, gen_client_kwargs


def test_is_anthropic_model():
    assert is_anthropic_model("claude-opus-4-8")
    assert is_anthropic_model("claude-sonnet-4-6")
    assert is_anthropic_model("claude-haiku-4-5")
    assert not is_anthropic_model("gemini-2.5-pro")
    assert not is_anthropic_model("llama-3.3-70b-versatile")


def test_sampling_unsupported_for_modern_claude_only():
    # 4.6+ / opus 4.7,4.8 / fable reject temperature/top_p/budget_tokens
    assert sampling_unsupported("claude-opus-4-8")
    assert sampling_unsupported("claude-sonnet-4-6")
    assert sampling_unsupported("claude-haiku-4-5")
    assert sampling_unsupported("claude-fable-5")
    # non-Claude models accept temperature
    assert not sampling_unsupported("gemini-2.5-pro")
    assert not sampling_unsupported("llama-3.3-70b-versatile")


def test_gen_client_kwargs_strips_temperature_for_modern_claude():
    # caller asks for temperature=0; modern Claude must drop it
    kw = gen_client_kwargs("claude-opus-4-8", temperature=0)
    assert "temperature" not in kw
    assert kw["model"] == "claude-opus-4-8"
    # non-Claude keeps temperature
    kw2 = gen_client_kwargs("gemini-2.5-pro", temperature=0)
    assert kw2["temperature"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_gen_model_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gen_model_probe'`.

- [ ] **Step 3: Implement the helpers**

Create `evals/gen_model_probe.py`:

```python
"""OFFLINE generation-model probe helpers (eval-only).

Builds a generation LLM client for an arbitrary model id so answer_eval_full can
swap ONLY generation (same retrieval, same independent judge) and attribute the
corr/faith delta to the model. Strips sampling params Claude 4.6+/Opus 4.7/4.8/
Fable reject (they 400 on temperature/top_p/top_k/budget_tokens).

NEVER imported by backend/rag.py or the request path.
"""
import re

# Claude families that reject temperature/top_p/top_k/budget_tokens and require
# adaptive thinking (per the claude-api skill). Matches opus-4-6+, sonnet-4-6,
# haiku-4-5, opus-4-7/4-8, fable-5.
_MODERN_CLAUDE_RE = re.compile(
    r"claude-(opus-4-(6|7|8)|sonnet-4-6|haiku-4-5|fable-5)", re.IGNORECASE
)


def is_anthropic_model(model_id: str) -> bool:
    return "claude" in (model_id or "").lower()


def sampling_unsupported(model_id: str) -> bool:
    """True if temperature/top_p/budget_tokens must be omitted for this model."""
    return bool(_MODERN_CLAUDE_RE.search(model_id or ""))


def gen_client_kwargs(model_id: str, temperature=0, **extra) -> dict:
    """Assemble constructor kwargs, dropping sampling params for modern Claude."""
    kw = {"model": model_id, **extra}
    if not sampling_unsupported(model_id):
        kw["temperature"] = temperature
    return kw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest evals/test_gen_model_probe.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/gen_model_probe.py evals/test_gen_model_probe.py
git commit -m "feat(evals): gen-model family detection + param stripping (Phase C Task 1)"
```

---

## Task 2: `build_gen_client` (Claude / Gemini, structured-output ready)

**Files:**
- Modify: `evals/gen_model_probe.py`
- Test: `evals/test_gen_model_probe.py` (append)

`build_gen_client` returns a LangChain chat model that `run_rag_query` can call `.with_structured_output(AdvisoryDraft)` on — `ChatAnthropic` for Claude ids, `ChatGoogleGenerativeAI` for Gemini ids. The factory is injectable so the unit test verifies selection + kwargs without network/keys.

- [ ] **Step 1: Append the failing test**

```python
from gen_model_probe import build_gen_client


def test_build_gen_client_selects_anthropic_and_strips_params():
    captured = {}
    def fake_anthropic(**kw):
        captured["anthropic"] = kw
        return "ANTHROPIC_CLIENT"
    def fake_gemini(**kw):
        captured["gemini"] = kw
        return "GEMINI_CLIENT"

    c = build_gen_client("claude-opus-4-8",
                         anthropic_factory=fake_anthropic, gemini_factory=fake_gemini)
    assert c == "ANTHROPIC_CLIENT"
    assert "temperature" not in captured["anthropic"]   # stripped for modern Claude
    assert captured["anthropic"]["model"] == "claude-opus-4-8"

    g = build_gen_client("gemini-2.5-pro",
                        anthropic_factory=fake_anthropic, gemini_factory=fake_gemini)
    assert g == "GEMINI_CLIENT"
    assert captured["gemini"]["temperature"] == 0       # kept for Gemini
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_gen_model_probe.py -k build_gen_client -v`
Expected: FAIL — `ImportError: cannot import name 'build_gen_client'`.

- [ ] **Step 3: Implement `build_gen_client`**

Add to `evals/gen_model_probe.py`:

```python
import os
from pathlib import Path


def _default_anthropic_factory(**kw):
    from langchain_anthropic import ChatAnthropic
    # max_tokens generous (advisory schema is small); adaptive thinking is the
    # default on 4.6+/4.8/Fable — do not pass a thinking budget.
    return ChatAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                         max_tokens=kw.pop("max_tokens", 4000), **kw)


def _default_gemini_factory(**kw):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(google_api_key=os.environ["GOOGLE_API_KEY"], **kw)


def build_gen_client(model_id, temperature=0,
                     anthropic_factory=_default_anthropic_factory,
                     gemini_factory=_default_gemini_factory):
    """Return a LangChain chat model for `model_id`, ready for
    `.with_structured_output(AdvisoryDraft)`. Factories are injected for testing."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    kw = gen_client_kwargs(model_id, temperature=temperature)
    if is_anthropic_model(model_id):
        return anthropic_factory(**kw)
    return gemini_factory(**kw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_gen_model_probe.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/gen_model_probe.py evals/test_gen_model_probe.py
git commit -m "feat(evals): build_gen_client for Claude/Gemini gen arms (Phase C Task 2)"
```

---

## Task 3 prerequisite: wire `--gen-model` into the harness ($0)

**Files:**
- Modify: `evals/answer_eval_full.py`

- [ ] **Step 1: Add the arg + pre-seed the generation LLM**

In `main()` parser:
```python
    ap.add_argument("--gen-model", default=None,
                    help="swap ONLY generation to this model id (e.g. claude-opus-4-8, "
                         "claude-sonnet-4-6, gemini-2.5-pro); same retrieval+judge. "
                         "Pair with --judge-provider gemini for an independent judge.")
```
After the provider block and BEFORE the run loop, mirror the `--two-step` pre-seed pattern (which sets `rag._deepinfra_llm`):
```python
    if args.gen_model:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from gen_model_probe import build_gen_client
        import services.rag as rag
        _gen = build_gen_client(args.gen_model)
        # Pre-seed the cached client run_rag_query reads, and point LLM_PRIMARY at it.
        # deepinfra slot is the non-streaming generation path the eval already uses.
        rag._deepinfra_llm = _gen
        config.LLM_PRIMARY = "deepinfra"
```
> The deepinfra slot is reused purely as the "non-streaming generation client" hook — `run_rag_query`'s `LLM_PRIMARY=="deepinfra"` branch calls `.with_structured_output(AdvisoryDraft)` on whatever client is in `rag._deepinfra_llm`, so a Claude/Gemini client works there unchanged. Keep `--judge-provider gemini` so the judge stays independent of the new gen model.

- [ ] **Step 2: Smoke-check it constructs (no spend — dry import)**

Run (no API call, just import + arg parse):
```bash
python -c "import sys; sys.path.insert(0,'evals'); from gen_model_probe import build_gen_client; print('import ok')"
```
Expected: `import ok` (build_gen_client is not invoked, so no key needed).

- [ ] **Step 3: Commit**

```bash
git add evals/answer_eval_full.py
git commit -m "feat(evals): --gen-model arm pre-seeds generation client (Phase C Task 3 prereq)"
```

---

## Task 3: Run the eval-only probe (MANUAL, cost-gated — STOP for OK per arm)

**Each arm spends generation tokens on the candidate model + Gemini judge. State the per-arm $ estimate (table in Handoff) and get explicit Taiwo OK before EACH arm.**

- [ ] **Step 1: Baseline is the existing DeepInfra-70B arm** (already measured: corr 21.6% / faith 75.7% on the curated set; or re-run for a same-session paired baseline).

- [ ] **Step 2: Probe arm (after OK) — cheapest candidate first**

```bash
python evals/answer_eval_full.py --provider deepinfra --judge-provider gemini \
  --gen-model claude-haiku-4-5 --eval-set evals/eval_set_v2_clean.jsonl \
  --sample 40 --seed 7 --dump evals/_capture_genmodel_haiku.jsonl
```
Then, on OK, the next arm (`claude-sonnet-4-6`), and optionally `claude-opus-4-8`. **Lead with the faith delta** — it's readable today; corr is directional until Phase 2's answer keys land (single-gold under-credits a redundant corpus). Record per-arm faith/corr + per-namespace.

- [ ] **Step 3: Record results + gitignore artifacts**

`evals/_capture_*.jsonl` is already gitignored. Update `PROGRESS.md` with the per-arm faith/corr table and the decision signal: does a stronger model lift faith materially above 75.7%, and is the lift worth the per-query cost? Then:
```bash
git add PROGRESS.md
git commit -m "docs(progress): Phase C gen-model probe results (eval-only)"
```

---

## Task 4: Decision gate (no code) — productionize or shelve

- [ ] **Step 1: Summarize the probe for Taiwo with an explicit recommendation**

Frame: (a) faith lift per arm vs the Groq-free 70B baseline, (b) per-query prod cost of each candidate, (c) whether corr is trustworthy yet (needs Phase 2). Recommend the cheapest arm that clears a material faith lift, or "shelve — lift doesn't justify ongoing cost." **Productionizing is Taiwo's call** (ongoing prod cost) — present numbers and stop.

---

## Task 5: Productionize the chosen model (GATED — touches backend, ongoing cost, STOP for OK)

**Only if Taiwo approves a specific model. This touches `backend/` → push to main auto-deploys to HF. Do NOT run as part of the probe.**

- [ ] **Step 1: Add the provider behind an env flag (fallback-safe)**

In `backend/config.py`: add `ANTHROPIC_API_KEY` + extend `LLM_PRIMARY` to accept `anthropic`. In `backend/services/rag.py`: add `_get_anthropic_llm()` (mirrors `_get_deepinfra_llm`, builds `ChatAnthropic` with sampling params omitted for modern Claude + adaptive thinking) and an `LLM_PRIMARY=="anthropic"` branch in `run_rag_query` that puts Anthropic first in the provider chain with Groq→Gemini as fallback (so a key/quota failure degrades safely, never hard-fails prod). TDD: a unit test that `_get_anthropic_llm` is used when `LLM_PRIMARY=anthropic` and falls back when the key is absent.

- [ ] **Step 2: Verify backend suite green, then ship per branch-safety**

`cd backend && pytest`. Merge to main only after tests + explicit Taiwo OK; push auto-deploys to HF. Post-deploy: a novel prod query spot-check (advisory renders, no schema errors in Space logs), and watch cost.

---

## Self-Review (completed)

- **Goal coverage:** eval-only gen-model swap → Task 1–2 (`gen_model_probe`) + Task 3-prereq (`--gen-model` pre-seed). Attribute delta to model (same retrieval/judge) → reuse `rag._deepinfra_llm` hook + `--judge-provider gemini`. Modern-Claude 400 avoidance → Task 1 `sampling_unsupported`/`gen_client_kwargs` + Task 2 `build_gen_client`. faith-readable-now / corr-needs-Phase-2 caveat → Handoff + Task 3 Step 2. Cost tension + don't-productionize-in-probe → Handoff + Task 4 gate + Task 5 gated. Productionization fallback-safety → Task 5 Step 1.
- **Placeholder scan:** pure helpers have complete code + failing tests + expected output; LLM steps (Task 3 arms, Task 5) are cost-gated manual runs with exact commands and the per-arm STOP. Task 3-prereq Step 1 names the exact arg, pre-seed site, and the reuse-deepinfra-slot rationale rather than pasting the 400-line harness.
- **Type consistency:** `is_anthropic_model(id)->bool`, `sampling_unsupported(id)->bool`, `gen_client_kwargs(id,temperature,**extra)->dict` (T1) feed `build_gen_client(id,...,factories)->chat_model` (T2), consumed in the harness as `rag._deepinfra_llm = build_gen_client(args.gen_model)` (T3-prereq). Model ids are bare strings from the candidate table (current per claude-api skill). The deepinfra-slot reuse is the single integration point, consistent across T3-prereq and the existing two-step arm.
