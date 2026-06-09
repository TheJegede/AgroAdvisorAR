"""Singleton sentence-transformer embedder for English retrieval.

The model is whatever EMBEDDING_MODEL_PATH points at (thenlper/gte-base by
default for the current gte index) — the class name is historical.
"""
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings
import config

_model: SentenceTransformer | None = None
MODEL_NAME = config.EMBEDDING_MODEL_PATH


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


class MiniLMEmbeddings(Embeddings):
    """LangChain-compatible EN embeddings (model = EMBEDDING_MODEL_PATH)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return get_model().encode(text, normalize_embeddings=True).tolist()
