"""Sparse (BM25) retrieval + Reciprocal Rank Fusion — pure, torch-free.

Shared by the hybrid eval spike and (once proven) the backend retrieval path.
BM25 recovers exact lexical / jargon / product-name matches that dense gte
embeddings miss (e.g. farmer slang "sprayer" vs the chunk's "calibration").
RRF fuses two ranked id lists by rank, not raw score, so incompatible BM25 and
cosine scales never need normalizing.
"""
import re

from rank_bm25 import BM25Okapi

_TOK = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> list[str]:
    return _TOK.findall(text.lower())


def build_bm25(docs: list[tuple[str, str]]):
    """docs: list of (chunk_id, text). Returns an opaque index for bm25_topk."""
    ids = [d[0] for d in docs]
    corpus = [_tok(d[1]) for d in docs]
    return BM25Okapi(corpus), ids


def bm25_topk(bm25_index, query: str, k: int) -> list[str]:
    bm25, ids = bm25_index
    scores = bm25.get_scores(_tok(query))
    ranked = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)
    return [ids[i] for i in ranked[:k]]


def rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion. Each id scores sum(1/(k+rank)) across the lists it
    appears in (rank 1-based); returns ids sorted by descending fused score."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, _id in enumerate(lst, start=1):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda d: scores[d], reverse=True)
