import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_bge_embeddings_produces_1024_dim(monkeypatch):
    """BGEEmbeddings.embed_query must return a list of 1024 floats."""
    import numpy as np

    fake_vec = np.zeros(1024, dtype="float32")

    class FakeModel:
        def encode(self, texts, normalize_embeddings=True):
            if isinstance(texts, list):
                return np.stack([fake_vec] * len(texts))
            return fake_vec

    import services.embedding as emb_mod
    monkeypatch.setattr(emb_mod, "_multilingual_model", FakeModel())

    from services.embedding import BGEEmbeddings
    bge = BGEEmbeddings()
    result = bge.embed_query("¿Cómo controlo el acaro del arroz?")
    assert len(result) == 1024
    assert all(isinstance(v, float) for v in result)


def test_detect_language_spanish():
    from services.classifier import detect_language
    assert detect_language("¿Cómo controlo el acaro del arroz en Arkansas?") == "es"


def test_detect_language_english():
    from services.classifier import detect_language
    assert detect_language("How do I control blast disease in rice?") == "en"


def test_detect_language_empty_defaults_en():
    from services.classifier import detect_language
    assert detect_language("") == "en"


def test_detect_language_short_text_defaults_en():
    from services.classifier import detect_language
    # Very short text raises LangDetectException — must default to 'en'
    assert detect_language("ok") == "en"
