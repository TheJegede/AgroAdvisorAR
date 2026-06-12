"""L3 verbatim-rate lever: directive + worked exemplar, flag-gated on L3_VERBATIM_RATE.

Stage 1 of docs/superpowers/plans/2026-06-12-l3-quote-exact-rate-generation-lever.md.
Default OFF so prod is unchanged until the paired eval measures a win.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.documents import Document
from utils.prompt import (
    build_system_prompt,
    L3_VERBATIM_RATE_BLOCK,
    L3_VERBATIM_EXEMPLAR,
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


# --- flag gating ----------------------------------------------------------

def test_l3_block_present_when_flag_on(monkeypatch):
    monkeypatch.setenv("L3_VERBATIM_RATE", "1")
    prompt = _build()
    assert L3_VERBATIM_RATE_BLOCK in prompt
    assert L3_VERBATIM_EXEMPLAR in prompt


def test_l3_block_present_in_informational_when_flag_on(monkeypatch):
    monkeypatch.setenv("L3_VERBATIM_RATE", "1")
    prompt = _build(intent="informational")
    assert L3_VERBATIM_RATE_BLOCK in prompt
    assert L3_VERBATIM_EXEMPLAR in prompt


def test_l3_block_absent_when_flag_unset(monkeypatch):
    monkeypatch.delenv("L3_VERBATIM_RATE", raising=False)
    prompt = _build()
    assert L3_VERBATIM_RATE_BLOCK not in prompt
    assert L3_VERBATIM_EXEMPLAR not in prompt


def test_l3_block_absent_when_flag_zero(monkeypatch):
    monkeypatch.setenv("L3_VERBATIM_RATE", "0")
    prompt = _build()
    assert L3_VERBATIM_RATE_BLOCK not in prompt


# --- the directive names the failure mode it prevents ---------------------

def test_l3_directive_names_verbatim_copy_behavior():
    low = L3_VERBATIM_RATE_BLOCK.lower()
    assert "verbatim" in low or "character-for-character" in low
    assert "rate" in low
    assert "round" in low or "paraphrase" in low  # the thing it forbids


# --- the exemplar actually DEMONSTRATES a verbatim copy --------------------

def test_l3_exemplar_copies_a_rate_verbatim():
    # A worked example must show the SAME rate string appearing both in the
    # retrieved-context line and in the output products_rates rate value.
    # The marker rate token therefore appears at least twice in the exemplar.
    assert L3_VERBATIM_EXEMPLAR.count("3.2 pt/A") >= 2
