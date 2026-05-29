"""Cross-encoder reranking stage (lazy singleton).

Reorders dense-retrieval candidates by query-passage relevance. Multilingual
(bge-reranker-v2-m3) so it serves EN and ES. Disabled by default — see
config.RERANK_ENABLED. The model is loaded only on first use, so when reranking
is off the heavy weights are never imported.
"""
import logging

import config

logger = logging.getLogger(__name__)

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading reranker %s", config.RERANK_MODEL)
        _reranker = CrossEncoder(config.RERANK_MODEL, max_length=512)
    return _reranker


def rerank(query: str, docs: list, top_n: int) -> list:
    """Return the top_n docs reordered by cross-encoder relevance.

    docs: LangChain Documents (uses .page_content). On any failure, returns the
    original dense order truncated to top_n (graceful degradation)."""
    if not docs:
        return docs
    try:
        model = _get_reranker()
        scores = model.predict([(query, d.page_content) for d in docs])
        ranked = [d for _, d in sorted(zip(scores, docs), key=lambda t: t[0], reverse=True)]
        return ranked[:top_n]
    except Exception:
        logger.warning("Reranking failed — falling back to dense order", exc_info=True)
        return docs[:top_n]
