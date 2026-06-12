"""Embed pre-extracted chunks from corpus_v3.jsonl and upsert to Pinecone.

Skips the expensive Docling extraction phase — reads the already-generated
en_chunks/corpus_v3.jsonl directly, embeds with gte-base, and upserts to
agroar-prod-gte-v3.

Usage:
    cd ingestion
    python embed_corpus.py [--index agroar-prod-gte-v3] [--jsonl en_chunks/corpus_v3.jsonl]
"""
import os
import json
import time
import argparse
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
DIMENSION = 768  # gte-base output dim
BATCH_SIZE = 64

DEFAULT_INDEX = "agroar-prod-gte-v3"
DEFAULT_JSONL = Path(__file__).parent / "en_chunks" / "corpus_v3.jsonl"


def get_or_create_index(api_key: str, index_name: str):
    from pinecone import Pinecone, ServerlessSpec
    pc = Pinecone(api_key=api_key)
    existing = [i.name for i in pc.list_indexes()]
    if index_name not in existing:
        print(f"Creating index '{index_name}' ({DIMENSION}-dim, cosine)...")
        pc.create_index(
            name=index_name,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(1)
        print("Index ready.")
    return pc.Index(index_name)


def load_chunks(jsonl_path: Path) -> list[dict]:
    chunks = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"Loaded {len(chunks)} chunks from {jsonl_path}")
    return chunks


def embed_and_upsert(chunks: list[dict], index_name: str) -> int:
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading {MODEL_NAME} on {device}...")
    model = SentenceTransformer(MODEL_NAME, device=device)
    index = get_or_create_index(PINECONE_API_KEY, index_name)

    total = 0
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]

        # Embed the pre-prefixed retrieval text for best retrieval quality
        texts = [c["retrieval_text"] for c in batch]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        # Group vectors by namespace for batched upsert
        by_ns: dict[str, list] = defaultdict(list)
        for chunk, emb in zip(batch, embeddings):
            ns = chunk.get("namespace") or chunk.get("crop_type", "general")
            by_ns[ns].append({
                "id": chunk["chunk_id"],
                "values": emb,
                "metadata": {
                    "text": chunk["source_text"],
                    "document_title": chunk.get("document_title", ""),
                    "section_heading": chunk.get("section_heading", ""),
                },
            })

        for ns, vectors in by_ns.items():
            index.upsert(vectors=vectors, namespace=ns)
            total += len(vectors)

        done = min(batch_start + BATCH_SIZE, len(chunks))
        print(f"  {done}/{len(chunks)} upserted")

    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Pinecone index name")
    parser.add_argument("--jsonl", default=str(DEFAULT_JSONL), help="Path to corpus JSONL")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL not found: {jsonl_path}")

    chunks = load_chunks(jsonl_path)
    total = embed_and_upsert(chunks, args.index)
    print(f"\nDone. Total upserted: {total} vectors to '{args.index}'")


if __name__ == "__main__":
    main()
