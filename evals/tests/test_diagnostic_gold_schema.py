# evals/tests/test_diagnostic_gold_schema.py
import json
import pytest
from evals.diagnostic.gold_schema import GoldRecord, load_gold_records, GoldSchemaError


def _valid_dict():
    return {
        "query": "How much paraquat per acre?",
        "namespace": "soybeans",
        "gold_found": True,
        "gold_answer": "Gramoxone SL 2.0 at 2.0-4.0 pt/acre",
        "gold_source": "MP44 Burndown section",
        "gold_snippet": "Gramoxone SL 2.0 ... 2.0 to 4.0 pt/A",
        "source_in_index": True,
        "rule_type": "flat",
        "human_bucket": "B2",
        "set_aside": False,
        "set_aside_reason": None,
    }


def test_valid_record_parses():
    rec = GoldRecord.from_dict(_valid_dict())
    assert rec.query.startswith("How much")
    assert rec.gold_found is True
    assert rec.rule_type == "flat"


def test_gold_found_true_requires_snippet():
    d = _valid_dict()
    d["gold_snippet"] = None
    with pytest.raises(GoldSchemaError, match="gold_snippet"):
        GoldRecord.from_dict(d)


def test_gold_found_false_allows_null_gold_fields():
    d = _valid_dict()
    d["gold_found"] = False
    d["gold_answer"] = None
    d["gold_source"] = None
    d["gold_snippet"] = None
    d["source_in_index"] = None
    rec = GoldRecord.from_dict(d)
    assert rec.gold_found is False


def test_bad_rule_type_rejected():
    d = _valid_dict()
    d["rule_type"] = "branching"
    with pytest.raises(GoldSchemaError, match="rule_type"):
        GoldRecord.from_dict(d)


def test_load_gold_records_reads_jsonl(tmp_path):
    p = tmp_path / "gold.jsonl"
    p.write_text(json.dumps(_valid_dict()) + "\n", encoding="utf-8")
    recs = load_gold_records(p)
    assert len(recs) == 1
    assert recs[0].namespace == "soybeans"
