"""Singleton sentence-transformer embedders: MiniLM (EN) and BGE-M3 (multilingual)."""
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings
import config

_model: SentenceTransformer | None = None
_multilingual_model: SentenceTransformer | None = None
MODEL_NAME = config.EMBEDDING_MODEL_PATH
MULTILINGUAL_MODEL_NAME = config.MULTILINGUAL_EMBEDDING_MODEL_PATH


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_multilingual_model() -> SentenceTransformer:
    global _multilingual_model
    if _multilingual_model is None:
        _multilingual_model = SentenceTransformer(MULTILINGUAL_MODEL_NAME)
    return _multilingual_model


class MiniLMEmbeddings(Embeddings):
    """LangChain-compatible EN embeddings (384-dim, fine-tuned MiniLM v2)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return get_model().encode(text, normalize_embeddings=True).tolist()


class BGEEmbeddings(Embeddings):
    """LangChain-compatible multilingual embeddings (1024-dim, BGE-M3)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_multilingual_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return get_multilingual_model().encode(text, normalize_embeddings=True).tolist()
