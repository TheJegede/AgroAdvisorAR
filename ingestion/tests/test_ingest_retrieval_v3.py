import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest_retrieval_v3 import build_vector  # noqa: E402


def test_build_vector_embeds_retrieval_text_but_preserves_source_text():
    record = {
        "chunk_id": "abc123",
        "namespace": "rice",
        "doc_id": "rice-guide-123",
        "document_title": "rice arkansas rice management guide 2026",
        "source_url": "file:///tmp/rice.pdf",
        "crop_type": "rice",
        "doc_type": "extension_pdf",
        "pub_year": 2026,
        "page_start": 12,
        "page_end": 13,
        "section_heading": "Preflood Nitrogen Timing",
        "subsection_heading": "",
        "parent_section_id": "section-123",
        "section_index": 3,
        "chunk_index": 2,
        "source_text": "Apply nitrogen to dry soil before establishing the flood.",
        "retrieval_header": (
            "rice arkansas rice management guide 2026 | Preflood Nitrogen Timing | "
            "nitrogen, flood - Apply nitrogen to dry soil before establishing the flood"
        ),
        "retrieval_text": (
            "rice arkansas rice management guide 2026 | Preflood Nitrogen Timing | "
            "nitrogen, flood - Apply nitrogen to dry soil before establishing the flood\n\n"
            "Apply nitrogen to dry soil before establishing the flood."
        ),
    }

    vector = build_vector(record, [0.1, 0.2, 0.3])

    assert vector["id"] == "abc123"
    assert vector["values"] == [0.1, 0.2, 0.3]
    assert vector["metadata"]["text"] == record["source_text"]
    assert vector["metadata"]["source_text"] == record["source_text"]
    assert vector["metadata"]["retrieval_text"] == record["retrieval_text"]
    assert vector["metadata"]["retrieval_header"] == record["retrieval_header"]
    assert vector["metadata"]["document_title"] == record["document_title"]
    assert vector["metadata"]["section_heading"] == "Preflood Nitrogen Timing"
    assert vector["metadata"]["page_start"] == 12
