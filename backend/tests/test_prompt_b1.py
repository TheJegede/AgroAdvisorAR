"""B1 reasoning-first scratchpad lever: optional `analysis` field generated FIRST
(quote exact context sentences, then derive the answer), flag-gated on
B1_REASONING_FIRST. Default OFF so prod is unchanged until the paired eval
measures a win. Plan: docs/superpowers/plans/2026-06-12-answer-quality-next-lever.md
(Phase B1)."""
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.documents import Document
from models.advisory import AdvisoryDraft, ContextMeta
from utils.prompt import (
    build_system_prompt,
    B1_REASONING_BLOCK,
    B1_REASONING_EXEMPLAR,
)


def _doc(title, section, content):
    return Document(page_content=content,
                    metadata={"document_title": title, "section_heading": section})


def _build(intent="diagnostic"):
    return build_system_prompt(
        soil_context={"available": False}, weather_context={"available": False},
        retrieved_docs=[_doc("Rice Guide", "Rates", "Apply Command at 1.6 pt/A.")],
        session_history=[], language="English", is_safety_critical=False,
        county_name="Arkansas", intent=intent,
    )


def _draft(**overrides):
    kwargs = dict(
        problem_summary="Test summary.",
        confidence="High",
        confidence_explanation="Stated in source.",
        language="en",
        context_meta=ContextMeta(
            soil_data_available=False, weather_data_available=False,
            county_fips="05031",
        ),
    )
    kwargs.update(overrides)
    return AdvisoryDraft(**kwargs)


# --- schema: analysis generates FIRST and is optional -----------------------

def test_analysis_is_first_schema_field():
    # Field declaration order = JSON schema property order = generation order.
    # The scratchpad must come before problem_summary so the model reasons
    # before committing to an answer.
    assert list(AdvisoryDraft.model_fields)[0] == "analysis"


def test_analysis_optional_defaults_none():
    draft = _draft()
    assert draft.analysis is None


# --- flag gating (default OFF until the paired eval measures a win) ---------

def test_b1_block_present_when_flag_on(monkeypatch):
    monkeypatch.setenv("B1_REASONING_FIRST", "1")
    prompt = _build()
    assert B1_REASONING_BLOCK in prompt
    assert B1_REASONING_EXEMPLAR in prompt


def test_b1_block_present_in_informational_when_flag_on(monkeypatch):
    monkeypatch.setenv("B1_REASONING_FIRST", "1")
    prompt = _build(intent="informational")
    assert B1_REASONING_BLOCK in prompt
    assert B1_REASONING_EXEMPLAR in prompt


def test_b1_block_present_by_default_when_flag_unset(monkeypatch):
    # Default ON after the measured win (paired n=40: corr 23.8%->27.5% helped 7/
    # hurt 3, faith 57.5%->65.0%) — present unless explicitly killed with "0".
    monkeypatch.delenv("B1_REASONING_FIRST", raising=False)
    prompt = _build()
    assert B1_REASONING_BLOCK in prompt
    assert B1_REASONING_EXEMPLAR in prompt


def test_b1_block_absent_when_flag_zero(monkeypatch):
    monkeypatch.setenv("B1_REASONING_FIRST", "0")
    prompt = _build()
    assert B1_REASONING_BLOCK not in prompt
    assert B1_REASONING_EXEMPLAR not in prompt


# --- the directive names the quote-then-answer behavior ---------------------

def test_b1_directive_names_quote_then_answer():
    low = B1_REASONING_BLOCK.lower()
    assert "analysis" in low
    assert "quote" in low
    assert "first" in low or "before" in low


# --- the exemplar DEMONSTRATES analysis-first with a verbatim quote ----------

def test_b1_exemplar_shows_analysis_first_with_verbatim_quote():
    assert '"analysis"' in B1_REASONING_EXEMPLAR
    assert B1_REASONING_EXEMPLAR.index('"analysis"') < B1_REASONING_EXEMPLAR.index('"problem_summary"')
    # The worked example must copy a context string verbatim into analysis:
    # the marker rate token appears in the retrieved-context line AND inside
    # the analysis value AND in the final answer fields (>= 3 occurrences).
    assert B1_REASONING_EXEMPLAR.count("0.5 oz/A") >= 3


# --- postprocess strips the scratchpad before guard/user ever see it ---------

def test_postprocess_strips_analysis(monkeypatch):
    import config
    import services.rag as rag
    monkeypatch.setattr(config, "NLI_CITATION_GUARD_ENABLED", False)
    draft = _draft(analysis="QUOTES: 'Apply Command at 1.6 pt/A.' — derive rate from this.")
    result = asyncio.run(rag._postprocess_async(draft, [], {}, {}, "05031"))
    assert result.analysis is None
