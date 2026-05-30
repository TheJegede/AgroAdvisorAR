import sys, types, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _Doc:
    def __init__(self, page_content):
        self.page_content = page_content


def _install_fake_st(predict_fn):
    """Inject a fake `sentence_transformers` module so reranker's lazy
    `from sentence_transformers import CrossEncoder` resolves to a stub — the
    real package loads torch native libs that segfault in CI. Returns the
    reranker module with its lazy singleton reset."""
    class _FakeCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs):
            return predict_fn(pairs)

    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = _FakeCrossEncoder
    sys.modules["sentence_transformers"] = fake

    reranker = importlib.import_module("services.reranker")
    reranker._reranker = None  # reset lazy singleton
    return reranker


def test_rerank_orders_by_score_and_trims():
    # Score = passage length → longest ranks first.
    reranker = _install_fake_st(lambda pairs: [float(len(p)) for _, p in pairs])
    docs = [_Doc("a"), _Doc("aaaaa"), _Doc("aaa")]  # len 1, 5, 3
    out = reranker.rerank("q", docs, top_n=2)
    assert [d.page_content for d in out] == ["aaaaa", "aaa"]


def test_rerank_empty_returns_empty():
    reranker = _install_fake_st(lambda pairs: [])
    assert reranker.rerank("q", [], top_n=5) == []


def test_rerank_falls_back_to_dense_order_on_failure():
    def _boom(pairs):
        raise RuntimeError("model exploded")

    reranker = _install_fake_st(_boom)
    docs = [_Doc("first"), _Doc("second"), _Doc("third")]
    out = reranker.rerank("q", docs, top_n=2)
    # Graceful degradation: original dense order, trimmed.
    assert [d.page_content for d in out] == ["first", "second"]
