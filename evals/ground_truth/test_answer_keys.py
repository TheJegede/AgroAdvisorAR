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
