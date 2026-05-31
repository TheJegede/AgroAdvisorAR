import json

from evals import eval_v3_ablation
from evals import filter_eval_by_section


def test_text_for_variant_keeps_source_text_plain():
    row = {
        "document_title": "Rice Guide",
        "section_heading": "Nitrogen",
        "retrieval_text": "Rice Guide | Nitrogen\n\nApply nitrogen at preflood.",
        "source_text": "Apply nitrogen at preflood.",
    }

    assert eval_v3_ablation.text_for_variant(row, "source_text") == "Apply nitrogen at preflood."
    assert eval_v3_ablation.text_for_variant(row, "retrieval_text").startswith("Rice Guide")


def test_title_section_source_variant_uses_metadata_header():
    row = {
        "document_title": "Rice Guide",
        "section_heading": "Water Management",
        "source_text": "Maintain flood after establishment.",
    }

    text = eval_v3_ablation.text_for_variant(row, "title_section_source")

    assert text == "Rice Guide | Water Management\n\nMaintain flood after establishment."


def test_ablation_summary_reports_candidate_recall():
    items = [
        {"chunk_id": "a", "namespace": "rice"},
        {"chunk_id": "b", "namespace": "rice"},
    ]
    rankings = [["x", "a"], ["c", "d", "b"]]

    summary = eval_v3_ablation.summarize(
        items,
        rankings,
        top_k=2,
        candidate_ks=(2, 3),
    )

    assert summary["count"] == 2
    assert summary["hit_at_k"] == 0.5
    assert summary["candidate_recall_at_2"] == 0.5
    assert summary["candidate_recall_at_3"] == 1.0
    assert summary["by_namespace"]["rice"]["count"] == 2


def test_filter_eval_by_section_tags_weak_sections_and_table_fragments(tmp_path):
    eval_path = tmp_path / "eval.jsonl"
    corpus_path = tmp_path / "corpus.jsonl"
    out_path = tmp_path / "kept.jsonl"
    tagged_path = tmp_path / "tagged.jsonl"
    report_path = tmp_path / "report.json"

    eval_rows = [
        {"chunk_id": "abstract-1", "namespace": "rice", "query": "q1"},
        {"chunk_id": "good-1", "namespace": "rice", "query": "q2"},
        {"chunk_id": "table-1", "namespace": "soybeans", "query": "q3"},
    ]
    corpus_rows = [
        {
            "chunk_id": "abstract-1",
            "document_title": "Study",
            "section_heading": "Abstract",
            "source_text": "Trial summary.",
        },
        {
            "chunk_id": "good-1",
            "document_title": "Guide",
            "section_heading": "Weed Control",
            "source_text": "Apply labeled herbicide rates.",
        },
        {
            "chunk_id": "table-1",
            "document_title": "Study",
            "section_heading": "Results",
            "source_text": "Treatment Rate Yield\nA 1.0 45\nB 2.0 47\nC 3.0 49",
        },
    ]
    eval_path.write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    corpus_path.write_text("\n".join(json.dumps(row) for row in corpus_rows) + "\n", encoding="utf-8")

    tagged = filter_eval_by_section.tag_rows(
        filter_eval_by_section.read_jsonl(eval_path),
        filter_eval_by_section.load_corpus(corpus_path),
        filter_eval_by_section.DEFAULT_WEAK_SECTIONS,
    )
    kept = [row for row in tagged if not row["gold_filter_reasons"]]
    filter_eval_by_section.write_jsonl(kept, out_path)
    filter_eval_by_section.write_jsonl(tagged, tagged_path)
    report = filter_eval_by_section.summarize(tagged)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    assert len(kept) == 1
    assert kept[0]["chunk_id"] == "good-1"
    assert report["filtered"] == 2
    assert report["reason_counts"]["weak_section:abstract"] == 1
    assert report["reason_counts"]["table_or_results_fragment"] == 1
