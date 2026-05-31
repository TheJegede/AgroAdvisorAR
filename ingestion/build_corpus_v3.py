"""Build the section-aware v3 corpus artifact.

This does not embed or upsert anything. It creates a JSONL corpus with stable
chunk IDs, page ranges, parent section IDs, source text, and contextual
retrieval text so retrieval-v3 experiments can run without touching production.

Run:
    python ingestion/build_corpus_v3.py
"""
import argparse
import json
from pathlib import Path

from chunker import SourcePage, chunk_sectioned_document
from extractor import extract_pages, extract_tables_as_text

RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
DEFAULT_OUT = Path(__file__).parent / "en_chunks" / "corpus_v3.jsonl"
CROP_TYPE_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _title_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ")


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_TYPE_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def _pages_with_tables(pdf_path: Path) -> list[SourcePage]:
    pages = [
        SourcePage(page_number=page.page_number, text=page.text)
        for page in extract_pages(str(pdf_path))
    ]
    tables = extract_tables_as_text(str(pdf_path))
    if tables:
        table_text = "\n\n".join(tables)
        page_number = pages[-1].page_number if pages else 1
        pages.append(SourcePage(page_number=page_number, text=f"Extracted Tables\n{table_text}"))
    return pages


def build_corpus(raw_pdfs_dir: Path = RAW_PDFS_DIR) -> list[dict]:
    records: list[dict] = []
    for pdf_path in sorted(raw_pdfs_dir.glob("*.pdf")):
        crop_type = _infer_crop_type(pdf_path.name)
        title = _title_from_path(pdf_path)
        source_url = f"file://{pdf_path.resolve()}"
        docs = chunk_sectioned_document(
            _pages_with_tables(pdf_path),
            document_title=title,
            source_url=source_url,
            crop_type=crop_type,
        )
        for doc in docs:
            records.append({
                **doc.metadata,
                "namespace": crop_type,
                "source_text": doc.page_content,
                "retrieval_header": doc.metadata["retrieval_header"],
                "retrieval_text": doc.metadata["retrieval_text"],
            })
    return records


def write_jsonl(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-pdfs-dir", type=Path, default=RAW_PDFS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    records = build_corpus(args.raw_pdfs_dir)
    write_jsonl(records, args.out)
    titled = sum(1 for r in records if r.get("document_title"))
    sectioned = sum(1 for r in records if r.get("section_heading"))
    print(f"Wrote {len(records)} chunks -> {args.out}")
    if records:
        print(f"document_title coverage: {titled / len(records):.1%}")
        print(f"section_heading coverage: {sectioned / len(records):.1%}")


if __name__ == "__main__":
    main()
