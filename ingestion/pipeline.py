"""Orchestrate: PDF → extract → chunk → embed → Pinecone upsert."""
import os
import json
import hashlib
import glob
import time
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv(Path(__file__).parent.parent / ".env")

from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document
from embedder import embed_and_upsert, MODEL_NAME

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")

RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
LOGS_DIR = Path(__file__).parent / "logs"
MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.json"

LOGS_DIR.mkdir(exist_ok=True)

# Filename convention: {crop_type}_{description}.pdf
# crop_type must be one of: rice, soybeans, poultry, general
CROP_TYPE_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_TYPE_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def _doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict) -> None:
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def run_pipeline(force_reindex: bool = False) -> dict:
    manifest = load_manifest()
    model = SentenceTransformer(MODEL_NAME)

    pdf_files = sorted(RAW_PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {RAW_PDFS_DIR}. Add PDFs and re-run.")
        return {"processed": 0, "skipped": 0, "failed": 0, "total_vectors": 0}

    print(f"Found {len(pdf_files)} PDFs.")
    log = {"processed": [], "skipped": [], "failed": []}
    total_vectors = 0

    for pdf_path in pdf_files:
        name = pdf_path.stem
        print(f"\nProcessing: {pdf_path.name}")

        try:
            text = extract_text(str(pdf_path))
            text_hash = _doc_hash(text)

            if not force_reindex and manifest.get(name, {}).get("hash") == text_hash:
                print(f"  Skipped (unchanged)")
                log["skipped"].append(name)
                continue

            # Also extract tables and append as text
            tables = extract_tables_as_text(str(pdf_path))
            if tables:
                text += "\n\n" + "\n\n".join(tables)

            crop_type = _infer_crop_type(pdf_path.name)
            docs = chunk_document(
                text,
                document_title=name.replace("_", " ").replace("-", " "),
                source_url=f"file://{pdf_path.resolve()}",
                crop_type=crop_type,
            )

            n = embed_and_upsert(
                docs,
                api_key=PINECONE_API_KEY,
                index_name=PINECONE_INDEX_NAME,
                namespace=crop_type,
                model=model,
            )
            total_vectors += n
            manifest[name] = {"hash": text_hash, "vectors": n, "crop_type": crop_type}
            print(f"  Upserted {n} vectors (namespace: {crop_type})")
            log["processed"].append({"file": name, "vectors": n, "crop_type": crop_type})

        except Exception as e:
            print(f"  FAILED: {e}")
            log["failed"].append({"file": name, "error": str(e)})

    save_manifest(manifest)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"run_{timestamp}.json"
    summary = {
        "processed": len(log["processed"]),
        "skipped": len(log["skipped"]),
        "failed": len(log["failed"]),
        "total_vectors": total_vectors,
        "details": log,
    }
    with open(log_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDone. Processed: {summary['processed']}, Skipped: {summary['skipped']}, "
          f"Failed: {summary['failed']}, Total vectors: {total_vectors}")
    print(f"Log: {log_path}")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-index all docs even if unchanged")
    args = parser.parse_args()
    run_pipeline(force_reindex=args.force)
