"""Singleton sentence-transformer embedder for query-time embedding."""
import os
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings

_model: SentenceTransformer | None = None
MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


class MiniLMEmbeddings(Embeddings):
    """LangChain-compatible embeddings wrapper."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = get_model()
        return model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        model = get_model()
        return model.encode(text, normalize_embeddings=True).tolist()
