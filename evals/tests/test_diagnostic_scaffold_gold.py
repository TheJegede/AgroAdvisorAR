# evals/tests/test_diagnostic_scaffold_gold.py
import json

from evals.diagnostic.scaffold_gold import (
    build_candidate_record,
    scaffold,
    iter_eval_items,
    write_candidates,
)
from evals.diagnostic.gold_schema import GoldRecord


def test_build_candidate_fills_mechanical_fields():
    rec = build_candidate_record("How much paraquat?", "soybeans", source_in_index=True)
    assert rec["query"] == "How much paraquat?"
    assert rec["namespace"] == "soybeans"
    assert rec["source_in_index"] is True


def test_build_candidate_leaves_human_fields_blank():
    rec = build_candidate_record("q", "rice", source_in_index=False)
    for field in ("gold_answer", "gold_source", "gold_snippet", "rule_type", "human_bucket"):
        assert rec[field] is None
    assert rec["gold_found"] is None
    assert rec["set_aside"] is False


def test_candidate_record_loads_under_gold_schema():
    # A scaffolded record must be a valid (unfinished) GoldRecord — no snippet
    # required because gold_found is unset.
    rec = build_candidate_record("q", "poultry", source_in_index=None)
    GoldRecord.from_dict(rec)  # must not raise


def test_scaffold_calls_title_lookup_with_document_title():
    seen = []

    def fake_lookup(title):
        seen.append(title)
        return title == "MP44 Weed Control"

    items = [
        {"query": "q1", "namespace": "soybeans", "document_title": "MP44 Weed Control"},
        {"query": "q2", "namespace": "rice", "document_title": "Rice Handbook"},
    ]
    records = scaffold(items, fake_lookup)
    assert seen == ["MP44 Weed Control", "Rice Handbook"]
    assert records[0]["source_in_index"] is True
    assert records[1]["source_in_index"] is False


def test_scaffold_missing_title_yields_null_source_flag():
    records = scaffold([{"query": "q", "namespace": "rice"}], lambda t: True)
    assert records[0]["source_in_index"] is None


def test_iter_eval_items_reads_jsonl(tmp_path):
    p = tmp_path / "eval.jsonl"
    p.write_text(
        json.dumps({"query": "q1", "namespace": "rice", "document_title": "Doc A", "chunk_text": "..."}) + "\n"
        + json.dumps({"query": "q2", "namespace": "soybeans", "document_title": "Doc B"}) + "\n",
        encoding="utf-8",
    )
    items = list(iter_eval_items(p))
    assert items == [
        {"query": "q1", "namespace": "rice", "document_title": "Doc A"},
        {"query": "q2", "namespace": "soybeans", "document_title": "Doc B"},
    ]


def test_write_candidates_roundtrips(tmp_path):
    out = tmp_path / "cand.jsonl"
    recs = [build_candidate_record("q1", "rice", True), build_candidate_record("q2", "soybeans", False)]
    write_candidates(recs, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["query"] == "q1"
