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


from ragas_eval import aggregate_scores

METRICS = ["faithfulness", "answer_relevancy",
           "llm_context_precision_without_reference", "non_llm_context_recall"]


def test_aggregate_means_per_crop_and_flags_rice_recall_provisional():
    rows = [
        {"namespace": "rice", "suppressed": False,
         "faithfulness": 1.0, "answer_relevancy": 0.8,
         "llm_context_precision_without_reference": 0.5,
         "non_llm_context_recall": 0.4},
        {"namespace": "rice", "suppressed": True,
         "faithfulness": 0.0, "answer_relevancy": 0.6,
         "llm_context_precision_without_reference": 0.5,
         "non_llm_context_recall": 0.6},
        {"namespace": "soybeans", "suppressed": False,
         "faithfulness": 0.5, "answer_relevancy": 1.0,
         "llm_context_precision_without_reference": 1.0,
         "non_llm_context_recall": 0.8},
    ]
    report = aggregate_scores(rows, METRICS)

    # per-crop means
    rice = report["by_crop"]["rice"]
    assert rice["count"] == 2
    assert rice["faithfulness"] == 0.5            # (1.0 + 0.0) / 2
    assert rice["answer_relevancy"] == 0.7        # (0.8 + 0.6) / 2
    soy = report["by_crop"]["soybeans"]
    assert soy["faithfulness"] == 0.5

    # overall
    assert report["overall"]["count"] == 3

    # by suppressed flag
    assert report["by_suppressed"][False]["count"] == 2
    assert report["by_suppressed"][True]["count"] == 1

    # rice context_recall flagged provisional (contaminated gold); others not
    assert report["by_crop"]["rice"]["non_llm_context_recall_provisional"] is True
    assert report["by_crop"]["soybeans"]["non_llm_context_recall_provisional"] is False


def test_aggregate_ignores_none_scores_in_means():
    rows = [
        {"namespace": "poultry", "suppressed": False,
         "faithfulness": 1.0, "answer_relevancy": None,
         "llm_context_precision_without_reference": None,
         "non_llm_context_recall": None},
        {"namespace": "poultry", "suppressed": False,
         "faithfulness": 0.0, "answer_relevancy": 0.5,
         "llm_context_precision_without_reference": None,
         "non_llm_context_recall": None},
    ]
    report = aggregate_scores(rows, METRICS)
    p = report["by_crop"]["poultry"]
    assert p["faithfulness"] == 0.5      # (1.0 + 0.0)/2
    assert p["answer_relevancy"] == 0.5  # only the one non-None value
    assert p["llm_context_precision_without_reference"] is None  # all None


from ragas_eval import format_report


def test_format_report_renders_crops_and_provisional_marker():
    report = {
        "overall": {"count": 3, "faithfulness": 0.5, "answer_relevancy": 0.7,
                    "llm_context_precision_without_reference": 0.66,
                    "non_llm_context_recall": 0.6},
        "by_crop": {
            "rice": {"count": 2, "faithfulness": 0.5, "answer_relevancy": 0.7,
                     "llm_context_precision_without_reference": 0.5,
                     "non_llm_context_recall": 0.5,
                     "non_llm_context_recall_provisional": True},
        },
        "by_suppressed": {
            False: {"count": 2, "faithfulness": 1.0, "answer_relevancy": 0.9,
                    "llm_context_precision_without_reference": 0.8,
                    "non_llm_context_recall": 0.7},
        },
    }
    text = format_report(report,
                         ["faithfulness", "answer_relevancy",
                          "llm_context_precision_without_reference",
                          "non_llm_context_recall"])
    assert "OVERALL" in text
    assert "rice" in text
    # provisional rice recall cell is marked
    assert "provisional" in text.lower()
    # suppressed segmentation present
    assert "suppressed" in text.lower()
