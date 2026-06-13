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
