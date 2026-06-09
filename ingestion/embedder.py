"""Embed document chunks and upsert to Pinecone."""
import os
import time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from langchain_core.documents import Document

MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
BATCH_SIZE = 64


def get_pinecone_index(api_key: str, index_name: str, dimension: int = 384):
    pc = Pinecone(api_key=api_key)
    existing = [i.name for i in pc.list_indexes()]
    if index_name not in existing:
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(1)
    return pc.Index(index_name)


def embed_and_upsert(
    documents: list[Document],
    *,
    api_key: str,
    index_name: str,
    namespace: str,
    model: SentenceTransformer | None = None,
) -> int:
    if not documents:
        return 0

    if model is None:
        model = SentenceTransformer(MODEL_NAME)

    dimension = model.get_sentence_embedding_dimension()
    index = get_pinecone_index(api_key, index_name, dimension=dimension)
    total_upserted = 0

    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i: i + BATCH_SIZE]
        texts = [doc.page_content for doc in batch]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        vectors = []
        for doc, emb in zip(batch, embeddings):
            vectors.append({
                "id": doc.metadata["chunk_id"],
                "values": emb,
                "metadata": {**doc.metadata, "text": doc.page_content},
            })

        index.upsert(vectors=vectors, namespace=namespace)
        total_upserted += len(vectors)

    return total_upserted
