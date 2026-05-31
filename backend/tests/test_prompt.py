import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.documents import Document
from utils.prompt import build_system_prompt, OUTPUT_INSTRUCTIONS


def _doc(title, section, content):
    return Document(page_content=content, metadata={"document_title": title, "section_heading": section})


def test_context_block_does_not_number_documents():
    # The prompt must NOT label chunks "Document N:" — the LLM echoes that into
    # citations/prose. Chunks are labeled by title/section instead.
    prompt = build_system_prompt(
        soil_context={"available": False}, weather_context={"available": False},
        retrieved_docs=[_doc("Rice Irrigation Guide", "Flow Rate", "GPM = D x D x L.")],
        session_history=[], language="English", is_safety_critical=False,
        county_name="Arkansas",
    )
    assert "Document 1:" not in prompt
    assert "Rice Irrigation Guide" in prompt        # title still present as the handle
    assert "GPM = D x D x L." in prompt              # content still present


def test_output_instructions_cite_by_title_not_document_number():
    # The citation instruction must tell the model to cite by document TITLE and
    # must not instruct a "Document N" convention.
    text = OUTPUT_INSTRUCTIONS.lower()
    assert "title" in text
    assert "document n" not in text and "document number" not in text
