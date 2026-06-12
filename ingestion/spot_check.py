"""Zero-cost retrieval spot-check for agroar-prod-gte-v3.

Embeds test queries locally with gte-base, hits Pinecone, prints top-3
retrieved document titles + section headings. No LLM calls.

Usage:
    cd ingestion
    python spot_check.py [--index agroar-prod-gte-v3] [--k 3]
"""
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")

TEST_QUERIES = [
    ("rice",      "What nitrogen rate should I apply for rice on silt loam soil?"),
    ("rice",      "How do I manage blast disease in Arkansas rice?"),
    ("soybeans",  "What herbicides control Palmer amaranth in soybeans?"),
    ("soybeans",  "When should I apply fungicide for sudden death syndrome in soybeans?"),
    ("poultry",   "How do I improve water quality in poultry houses?"),
]


def run_check(index_name: str, k: int):
    import torch
    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading {MODEL_NAME} on {device}...")
    model = SentenceTransformer(MODEL_NAME, device=device)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"\nIndex: {index_name}")
    for ns, info in stats.namespaces.items():
        print(f"  {ns}: {info.vector_count} vectors")

    print(f"\n{'='*60}")
    all_pass = True
    for namespace, query in TEST_QUERIES:
        embedding = model.encode(query, normalize_embeddings=True).tolist()
        results = index.query(
            vector=embedding,
            top_k=k,
            namespace=namespace,
            include_metadata=True,
        )
        matches = results.get("matches", [])
        ok = len(matches) > 0
        if not ok:
            all_pass = False

        status = "OK" if ok else "MISS"
        print(f"\n[{status}] [{namespace}] {query}")
        if matches:
            for i, m in enumerate(matches, 1):
                title = m["metadata"].get("document_title", "?")
                section = m["metadata"].get("section_heading", "")
                score = m["score"]
                snippet = m["metadata"].get("text", "")[:80].replace("\n", " ")
                print(f"  {i}. [{score:.3f}] {title}")
                if section:
                    print(f"       section: {section}")
                print(f"       text: {snippet}...")
        else:
            print("  No results returned!")

    print(f"\n{'='*60}")
    print(f"Result: {'ALL PASS' if all_pass else 'SOME MISSES — check above'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="agroar-prod-gte-v3")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    run_check(args.index, args.k)


if __name__ == "__main__":
    main()
