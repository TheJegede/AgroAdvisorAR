"""B2 format-tax probe: unconstrained generation + parse-or-repair to AdvisoryDraft.

All offline — no API calls. The repair path is exercised with a fake formatter."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "backend"), str(ROOT / "evals")):
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
