import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ingestion"))

import tiktoken
from chunker import chunk_document

# tiktoken (no torch) — this anaconda+pytest env segfaults loading transformers,
# so chunk sizing + this test both use tiktoken rather than the gte tokenizer.
_ENC = tiktoken.get_encoding("cl100k_base")


def _long_text():
    # Many tokens of varied agronomic prose so the splitter must produce >1 chunk.
    para = (
        "Sprayer calibration is essential for accurate herbicide application. "
        "Determine gallons per acre using the ounce method before mixing the tank. "
        "Nitrogen deficiency in rice shows as yellowing of the lower leaves. "
    )
    return (para * 200)


def test_chunks_sized_by_token_budget():
    docs = chunk_document(
        _long_text(),
        document_title="test doc",
        source_url="file://x",
        crop_type="rice",
    )
    assert len(docs) > 1
    token_lens = [len(_ENC.encode(d.page_content)) for d in docs]
    # Stays within the configured budget (chunk_size + overlap boundary tolerance),
    # safely under gte-base's 512-token input limit.
    assert max(token_lens) <= 450
    # Chunks are substantial — mean well above the old ~100-token (512-char) regime.
    assert sum(token_lens) / len(token_lens) > 250


def test_metadata_contract_preserved():
    docs = chunk_document(
        "Calibrate the sprayer before applying herbicide. " * 30,
        document_title="soybeans recommended chemicals 2024",
        source_url="file://x",
        crop_type="soybeans",
    )
    meta = docs[0].metadata
    assert set(meta) >= {"chunk_id", "document_title", "section_heading", "crop_type", "chunk_index"}
    assert meta["document_title"] == "soybeans recommended chemicals 2024"
    assert meta["crop_type"] == "soybeans"
