"""Upsert translated ES chunks from ingestion/es_chunks/corpus_es.jsonl into Pinecone.

Run after translate_corpus.py:
    python ingestion/ingest_es_chunks.py

Set PINECONE_MULTILINGUAL_INDEX_NAME to override index name (default: agroar-prod-multilingual).
Uses BAAI/bge-m3 (1024-dim) embeddings.
"""
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
INDEX_NAME = os.environ.get("PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual")
BGE_MODEL_NAME = os.environ.get("MULTILINGUAL_EMBEDDING_MODEL_PATH", "BAAI/bge-m3")
INPUT_PATH = Path(__file__).parent / "es_chunks" / "corpus_es.jsonl"
BATCH_SIZE = 64
DIMENSION = 1024


def _get_or_create_index(pc: Pinecone):
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"Creating index '{INDEX_NAME}' ({DIMENSION}-dim)...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


def ingest_es_chunks() -> int:
    if not INPUT_PATH.exists():
        print(f"Input not found: {INPUT_PATH}. Run translate_corpus.py first.")
        return 0

    rows = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No chunks in input file.")
        return 0

    print(f"Loading BGE-M3 model: {BGE_MODEL_NAME}")
    model = SentenceTransformer(BGE_MODEL_NAME)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc)

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        texts = [r["text"] for r in batch]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        by_namespace: dict[str, list] = {}
        for record, emb in zip(batch, embeddings):
            chunk_id = record.get("chunk_id", f"es_{i}_{len(by_namespace)}")
            ns = record.get("crop_type", "general")
            vector = {
                "id": chunk_id,
                "values": emb,
                "metadata": {k: v for k, v in record.items() if k != "text"},
            }
            by_namespace.setdefault(ns, []).append(vector)

        for ns, ns_vectors in by_namespace.items():
            index.upsert(vectors=ns_vectors, namespace=ns)
            total += len(ns_vectors)

        print(f"  Batch {i // BATCH_SIZE + 1}: {sum(len(v) for v in by_namespace.values())} vectors")

    print(f"\nTotal upserted: {total} vectors to '{INDEX_NAME}'")
    return total


if __name__ == "__main__":
    ingest_es_chunks()
