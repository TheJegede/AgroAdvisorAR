"""One-time setup: create the agroar-prod-multilingual Pinecone index (1024-dim).

Run once before ingesting any Spanish corpus content:
    python ingestion/create_multilingual_index.py

Set PINECONE_MULTILINGUAL_INDEX_NAME env var to override the default index name.
"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
INDEX_NAME = os.environ.get("PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual")
DIMENSION = 1024


def create_index() -> None:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME in existing:
        print(f"Index '{INDEX_NAME}' already exists. Nothing to do.")
        return

    print(f"Creating '{INDEX_NAME}' ({DIMENSION}-dim, cosine, serverless us-east-1)...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)
    print(f"Index '{INDEX_NAME}' ready.")


if __name__ == "__main__":
    create_index()
