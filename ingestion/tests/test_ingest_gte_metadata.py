import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.documents import Document
from ingest_en_gte import build_vector


def test_build_vector_carries_title_and_section():
    doc = Document(
        page_content="Calibrate the sprayer before applying herbicide.",
        metadata={
            "chunk_id": "abc123",
            "document_title": "soybeans recommended chemicals 2024",
            "section_heading": "Sprayer Calibration",
            "crop_type": "soybeans",
        },
    )
    vec = build_vector(doc, embedding=[0.1, 0.2, 0.3])
    assert vec["id"] == "abc123"
    assert vec["values"] == [0.1, 0.2, 0.3]
    assert vec["metadata"]["text"] == "Calibrate the sprayer before applying herbicide."
    assert vec["metadata"]["namespace"] == "soybeans"
    assert vec["metadata"]["document_title"] == "soybeans recommended chemicals 2024"
    assert vec["metadata"]["section_heading"] == "Sprayer Calibration"
