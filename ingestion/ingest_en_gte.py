"""Build the EN gte-base retrieval index from the raw PDFs (single source of truth).

Re-chunks every PDF in raw_pdfs/ via chunker.chunk_document (token-sized chunks +
document_title/section_heading metadata), embeds with thenlper/gte-base (768-dim),
and upserts to a NEW Pinecone index (default agroar-prod-gte-v2 — never clobbers
the live agroar-prod-gte). Carrying document_title lets the citation guard validate
real titles instead of being dead on a titleless index.

Run once:
    python ingestion/ingest_en_gte.py

Then point the backend EN retrieval at it (after eval-verifying the delta):
    EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2

Note: torch/sentence_transformers are imported lazily inside main() so this module
can be imported under pytest (this env segfaults loading torch during collection).
"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec
from langchain_core.documents import Document

from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
# Build into a NEW index by default — never clobber the live agroar-prod-gte.
INDEX_NAME = os.environ.get("EN_GTE_INDEX_NAME", "agroar-prod-gte-v2")
MODEL_NAME = os.environ.get("EN_GTE_MODEL", "thenlper/gte-base")
RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
BATCH_SIZE = 64
DIMENSION = 768

CROP_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def build_vector(doc: Document, embedding: list) -> dict:
    """Pinecone vector dict for one chunk, carrying title/section metadata so the
    citation guard can validate real document titles."""
    ns = doc.metadata["crop_type"]
    return {
        "id": doc.metadata["chunk_id"],
        "values": embedding,
        "metadata": {
            "text": doc.page_content,
            "namespace": ns,
            "document_title": doc.metadata.get("document_title", ""),
            "section_heading": doc.metadata.get("section_heading", ""),
        },
    }


def chunk_all_pdfs() -> list:
    docs = []
    for pdf_path in sorted(RAW_PDFS_DIR.glob("*.pdf")):
        crop = _infer_crop_type(pdf_path.name)
        text = extract_text(str(pdf_path))
        tables = extract_tables_as_text(str(pdf_path))
        if tables:
            text += "\n\n" + "\n\n".join(tables)
        title = pdf_path.stem.replace("_", " ").replace("-", " ")
        docs.extend(chunk_document(
            text, document_title=title,
            source_url=f"file://{pdf_path.resolve()}", crop_type=crop,
        ))
    return docs


def _get_or_create_index(pc: Pinecone):
    if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
        print(f"Creating index '{INDEX_NAME}' ({DIMENSION}-dim, cosine)...")
        pc.create_index(
            name=INDEX_NAME, dimension=DIMENSION, metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


def main() -> int:
    docs = chunk_all_pdfs()
    if not docs:
        print(f"No chunks built from {RAW_PDFS_DIR}.")
        return 0
    print(f"Built {len(docs)} chunks from raw PDFs. Loading {MODEL_NAME}...")
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc)

    total = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        embs = model.encode(
            [d.page_content for d in batch],
            normalize_embeddings=True, batch_size=BATCH_SIZE,
        ).tolist()
        by_ns: dict[str, list] = {}
        for d, emb in zip(batch, embs):
            v = build_vector(d, emb)
            by_ns.setdefault(v["metadata"]["namespace"], []).append(v)
        for ns, vecs in by_ns.items():
            index.upsert(vectors=vecs, namespace=ns)
            total += len(vecs)
        print(f"  {min(i + BATCH_SIZE, len(docs))}/{len(docs)} upserted")

    print(f"\nTotal upserted: {total} vectors to '{INDEX_NAME}'")
    return total


if __name__ == "__main__":
    main()
