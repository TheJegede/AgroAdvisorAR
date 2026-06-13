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
