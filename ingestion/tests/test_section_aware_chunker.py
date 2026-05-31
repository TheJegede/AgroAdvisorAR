import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_corpus_v3 import write_jsonl  # noqa: E402
from chunker import (  # noqa: E402
    SourcePage,
    chunk_sectioned_document,
    infer_pub_year,
    make_doc_id,
    split_section_blocks,
)


def _pages():
    return [
        SourcePage(
            page_number=1,
            text=(
                "Introduction\n"
                "Rice irrigation timing depends on soil texture and field history.\n"
                "Preflood Nitrogen Timing\n"
                "Apply nitrogen to dry soil before establishing the flood.\n"
            ),
        ),
        SourcePage(
            page_number=2,
            text=(
                "Disease Management\n"
                "Scout fields weekly and confirm disease pressure before treatment.\n"
            ),
        ),
    ]


def test_split_section_blocks_preserves_headings_and_page_ranges():
    sections = split_section_blocks(_pages())
    headings = [section.heading for section in sections]
    assert "Introduction" in headings
    assert "Preflood Nitrogen Timing" in headings
    assert "Disease Management" in headings

    disease = next(section for section in sections if section.heading == "Disease Management")
    assert disease.page_start == 2
    assert disease.page_end == 2
    assert disease.parent_section_id.startswith("section-")


def test_chunk_sectioned_document_adds_v3_metadata_and_stable_ids():
    kwargs = {
        "document_title": "rice arkansas rice production handbook 2026",
        "source_url": "file:///tmp/rice.pdf",
        "crop_type": "rice",
    }
    docs = chunk_sectioned_document(_pages(), **kwargs)
    docs_again = chunk_sectioned_document(_pages(), **kwargs)

    assert [doc.metadata["chunk_id"] for doc in docs] == [
        doc.metadata["chunk_id"] for doc in docs_again
    ]
    assert all(doc.metadata["document_title"] == kwargs["document_title"] for doc in docs)
    assert all(doc.metadata["doc_id"] == make_doc_id(kwargs["document_title"], kwargs["source_url"]) for doc in docs)
    assert all(doc.metadata["crop_type"] == "rice" for doc in docs)
    assert all(doc.metadata["doc_type"] == "extension_pdf" for doc in docs)
    assert all(doc.metadata["page_start"] is not None for doc in docs)
    assert all(doc.metadata["page_end"] is not None for doc in docs)
    assert all(doc.metadata["parent_section_id"] for doc in docs)
    assert all("retrieval_header" in doc.metadata for doc in docs)
    assert all("retrieval_text" in doc.metadata for doc in docs)

    preflood = next(doc for doc in docs if doc.metadata["section_heading"] == "Preflood Nitrogen Timing")
    assert preflood.metadata["pub_year"] == 2026
    assert preflood.metadata["retrieval_header"].startswith(
        "rice arkansas rice production handbook 2026 | Preflood Nitrogen Timing"
    )
    assert "nitrogen" in preflood.metadata["retrieval_header"]
    assert preflood.metadata["retrieval_text"].startswith(preflood.metadata["retrieval_header"])
    assert preflood.page_content in preflood.metadata["retrieval_text"]


def test_infer_pub_year_returns_latest_year():
    assert infer_pub_year("2019 rice study", "updated 2026") == 2026
    assert infer_pub_year("no year here") is None


def test_write_jsonl_round_trips_records(tmp_path):
    out = tmp_path / "corpus_v3.jsonl"
    write_jsonl([
        {
            "chunk_id": "abc",
            "document_title": "rice guide",
            "section_heading": "Irrigation",
            "source_text": "source",
            "retrieval_header": "rice guide | Irrigation",
            "retrieval_text": "rice guide | Irrigation\nsource",
        }
    ], out)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["chunk_id"] == "abc"
    assert rows[0]["section_heading"] == "Irrigation"
