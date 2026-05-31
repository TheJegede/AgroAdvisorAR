"""Scratch script to check Pinecone vector metadata.

Queries a small sample of vectors from a namespace and prints their metadata structure.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from pinecone import Pinecone

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte")

def main():
    if not PINECONE_API_KEY:
        print("Error: PINECONE_API_KEY not set.")
        sys.exit(1)

    print(f"Connecting to Pinecone index: {INDEX_NAME}...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    try:
        index = pc.Index(INDEX_NAME)
        stats = index.describe_index_stats()
        print(f"Index Stats:\n{stats}\n")

        # Query a sample vector from poultry, rice, or soybeans namespace
        # We query with a non-zero dummy vector so cosine similarity calculations succeed
        dummy_vector = [0.1] * 768
        for ns in ["poultry", "rice", "soybeans"]:
            print(f"--- Namespace: {ns} ---")
            results = index.query(
                vector=dummy_vector,
                top_k=2,
                namespace=ns,
                include_metadata=True
            )
            
            matches = results.get("matches", [])
            if not matches:
                print("No vectors found.")
                continue
                
            for match in matches:
                print(f"Vector ID: {match['id']}")
                print(f"Score: {match['score']}")
                meta = match.get("metadata", {})
                print("Metadata keys:", list(meta.keys()))
                print("Metadata values:")
                for k, v in meta.items():
                    val_str = str(v)
                    if len(val_str) > 100:
                        val_str = val_str[:100] + "... [truncated]"
                    print(f"  {k}: {val_str}")
                print()
    except Exception as e:
        print(f"Error querying Pinecone: {e}")

if __name__ == "__main__":
    main()
