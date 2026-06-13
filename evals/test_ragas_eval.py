import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from ragas_eval import load_dump, load_gold_reference_contexts


def _write_jsonl(tmp_path, name, rows):
    p = tmp_path / name
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_load_dump_reads_records(tmp_path):
    dump = _write_jsonl(tmp_path, "dump.jsonl", [
        {"query": "q1", "namespace": "rice", "suppressed": False,
         "answer": "a1", "contexts": ["c1", "c2"]},
    ])
    recs = load_dump(dump)
    assert len(recs) == 1
    assert recs[0]["answer"] == "a1"
    assert recs[0]["contexts"] == ["c1", "c2"]


def test_gold_reference_contexts_groups_chunks_by_query(tmp_path):
    gold = _write_jsonl(tmp_path, "gold.jsonl", [
        {"query": "q1", "chunk_text": "gold-a", "namespace": "rice"},
        {"query": "q1", "chunk_text": "gold-b", "namespace": "rice"},
        {"query": "q2", "chunk_text": "gold-c", "namespace": "soybeans"},
    ])
    m = load_gold_reference_contexts(gold)
    assert m["q1"] == ["gold-a", "gold-b"]
    assert m["q2"] == ["gold-c"]


from ragas_eval import build_samples


def test_build_samples_pairs_dump_with_gold_and_metadata():
    dump = [
        {"query": "q1", "namespace": "rice", "suppressed": False,
         "answer": "a1", "contexts": ["c1", "c2"]},
        {"query": "q2", "namespace": "soybeans", "suppressed": True,
         "answer": "a2", "contexts": ["c3"]},
    ]
    gold = {"q1": ["gold-a", "gold-b"]}  # q2 has no gold

    samples, meta = build_samples(dump, gold)

    assert len(samples) == 2
    # sample 0
    assert samples[0].user_input == "q1"
    assert samples[0].response == "a1"
    assert samples[0].retrieved_contexts == ["c1", "c2"]
    assert samples[0].reference_contexts == ["gold-a", "gold-b"]
    # sample 1 — no gold -> empty reference_contexts (reference-free metrics still run)
    assert samples[1].reference_contexts == []
    # metadata aligned by index for aggregation
    assert meta[0] == {"namespace": "rice", "suppressed": False}
    assert meta[1] == {"namespace": "soybeans", "suppressed": True}
