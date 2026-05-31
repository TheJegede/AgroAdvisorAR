"""Embed and upsert the retrieval-v3 corpus.

This script reads ``ingestion/en_chunks/corpus_v3.jsonl`` and embeds the
contextual ``retrieval_text`` field while preserving ``source_text`` as the
display/citation text in Pinecone metadata. It is an experiment path and does
not touch the current production index unless explicitly configured.

Run:
    python ingestion/ingest_retrieval_v3.py
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec  # noqa: E402

DEFAULT_CORPUS = Path(__file__).parent / "en_chunks" / "corpus_v3.jsonl"
DEFAULT_INDEX = os.environ.get("RETRIEVAL_V3_INDEX_NAME", "agroar-prod-retrieval-v3")
DEFAULT_MODEL = (
    os.environ.get("RETRIEVAL_V3_MODEL")
    or os.environ.get("EN_GTE_MODEL")
    or "thenlper/gte-base"
)
BATCH_SIZE = 64


def load_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_vector(record: dict, embedding: list[float]) -> dict:
    namespace = record.get("namespace") or record.get("crop_type") or "general"
    source_text = record["source_text"]
    return {
        "id": record["chunk_id"],
        "values": embedding,
        "metadata": {
            "text": source_text,
            "source_text": source_text,
            "retrieval_text": record["retrieval_text"],
            "retrieval_header": record.get("retrieval_header", ""),
            "namespace": namespace,
            "doc_id": record.get("doc_id", ""),
            "document_title": record.get("document_title", ""),
            "source_url": record.get("source_url", ""),
            "crop_type": record.get("crop_type", namespace),
            "doc_type": record.get("doc_type", ""),
            "pub_year": record.get("pub_year", 0),
            "page_start": record.get("page_start", 0),
            "page_end": record.get("page_end", 0),
            "section_heading": record.get("section_heading", ""),
            "subsection_heading": record.get("subsection_heading", ""),
            "parent_section_id": record.get("parent_section_id", ""),
            "section_index": record.get("section_index", 0),
            "chunk_index": record.get("chunk_index", 0),
        },
    }


def _get_or_create_index(pc: Pinecone, index_name: str, dimension: int):
    if index_name not in [i.name for i in pc.list_indexes()]:
        print(f"Creating index '{index_name}' ({dimension}-dim, cosine)...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(1)
    return pc.Index(index_name)


def _batched(records: list[dict], batch_size: int) -> Iterable[list[dict]]:
    for i in range(0, len(records), batch_size):
        yield records[i: i + batch_size]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    records = load_records(args.corpus)
    if not records:
        print(f"No records found in {args.corpus}.")
        return 0

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model)
    dimension = model.get_sentence_embedding_dimension()
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = _get_or_create_index(pc, args.index, dimension)

    total = 0
    for batch in _batched(records, args.batch_size):
        embeddings = model.encode(
            [record["retrieval_text"] for record in batch],
            normalize_embeddings=True,
            batch_size=args.batch_size,
        ).tolist()
        by_ns: dict[str, list[dict]] = {}
        for record, embedding in zip(batch, embeddings):
            vector = build_vector(record, embedding)
            by_ns.setdefault(vector["metadata"]["namespace"], []).append(vector)
        for namespace, vectors in by_ns.items():
            index.upsert(vectors=vectors, namespace=namespace)
            total += len(vectors)
        print(f"  {total}/{len(records)} upserted")

    print(f"\nTotal upserted: {total} vectors to '{args.index}'")
    return total


if __name__ == "__main__":
    main()
