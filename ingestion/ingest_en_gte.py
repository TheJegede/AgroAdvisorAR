"""Build the EN gte-base retrieval index from the cached corpus.

Embeds ingestion/en_chunks/corpus_en.jsonl with thenlper/gte-base (768-dim) and
upserts to a new Pinecone index (default agroar-prod-gte), preserving chunk_ids
and crop namespaces so the existing eval gold ids still match. GPU auto-used.

Run once:
    python ingestion/ingest_en_gte.py

Then point the backend EN retrieval at it:
    EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte
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
INDEX_NAME = os.environ.get("EN_GTE_INDEX_NAME", "agroar-prod-gte")
MODEL_NAME = os.environ.get("EN_GTE_MODEL", "thenlper/gte-base")
INPUT_PATH = Path(__file__).parent / "en_chunks" / "corpus_en.jsonl"
BATCH_SIZE = 64
DIMENSION = 768


def _get_or_create_index(pc: Pinecone):
    if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
        print(f"Creating index '{INDEX_NAME}' ({DIMENSION}-dim, cosine, serverless us-east-1)...")
        pc.create_index(
            name=INDEX_NAME, dimension=DIMENSION, metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"Input not found: {INPUT_PATH}. Generate the EN corpus cache first "
              f"(e.g. run evals/generate_synthetic_queries.py once, or the ingestion pipeline).")
        return 0
    rows = [json.loads(l) for l in open(INPUT_PATH, encoding="utf-8") if l.strip()]
    if not rows:
        print("No chunks in input.")
        return 0

    print(f"Loading {MODEL_NAME}...")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc)

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        texts = [r["text"] for r in batch]
        embs = model.encode(texts, normalize_embeddings=True, batch_size=BATCH_SIZE).tolist()
        by_ns: dict[str, list] = {}
        for r, emb in zip(batch, embs):
            ns = r.get("namespace", "general")
            by_ns.setdefault(ns, []).append({
                "id": r["chunk_id"],
                "values": emb,
                "metadata": {"text": r["text"], "namespace": ns},
            })
        for ns, vecs in by_ns.items():
            index.upsert(vectors=vecs, namespace=ns)
            total += len(vecs)
        print(f"  {min(i + BATCH_SIZE, len(rows))}/{len(rows)} chunks upserted")

    print(f"\nTotal upserted: {total} vectors to '{INDEX_NAME}'")
    return total


if __name__ == "__main__":
    main()
