"""OFFLINE rice gold-label curation (eval-only, $0 for the pure helpers).

Re-points rice gold off the non-answer-bearing "br wells ... research studies"
yearly-volume TOCs onto dedicated topical rice docs drawn from corpus_v3, by an
INDEPENDENT keyword search (not the prod gte embedder, blind to eval dumps) so
the post-curation rice headline stays honest. See the design spec:
docs/superpowers/specs/2026-06-12-rice-gold-curation-design.md

NEVER imported by backend/rag.py or the request path.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CLEAN_SET = Path(__file__).parent / "eval_set_v2_clean.jsonl"
CORPUS_V3 = REPO_ROOT / "ingestion" / "en_chunks" / "corpus_v3.jsonl"

# The non-answer-bearing yearly research-volume signature. Targets the "br wells
# ... research studies" compilations specifically; deliberately does NOT match
# answer-bearing docs that merely contain a year (management guide, perf trials).
_YEARLY_VOLUME_RE = re.compile(r"br wells.*research stud", re.IGNORECASE)


def flag_yearly_volume_gold(rows: list[dict]) -> list[dict]:
    """Return the rice rows whose gold document_title is a yearly-volume TOC."""
    return [
        r for r in rows
        if r.get("namespace") == "rice"
        and _YEARLY_VOLUME_RE.search(r.get("document_title", ""))
    ]


_WORD_RE = re.compile(r"[a-z]{3,}")  # 3+ letter lowercase tokens
# Generic agronomy/question stopwords that don't discriminate topic.
_STOP = {
    "the", "and", "for", "with", "are", "can", "you", "your", "how", "what",
    "much", "many", "should", "would", "could", "rice", "field", "fields",
    "crop", "crops", "farm", "use", "using", "get", "got", "put", "have",
    "this", "that", "from", "out", "about", "into", "they", "them", "some",
    "best", "good", "more", "less", "when", "where", "which", "will", "does",
}


def _tokens(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def load_corpus_v3(path=CORPUS_V3) -> list[dict]:
    """Load the v3 corpus (one JSON object per line)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def candidate_chunks(question: str, corpus: list[dict], k: int = 10) -> list[dict]:
    """Rank rice corpus chunks by term overlap with the question, EXCLUDING the
    yearly-volume TOCs. Independent of the prod gte retrieval (keyword only).

    Returns up to k dicts: {chunk_id, document_title, source_text, score}.
    """
    q = _tokens(question)
    scored = []
    for c in corpus:
        if c.get("namespace") != "rice":
            continue
        if _YEARLY_VOLUME_RE.search(c.get("document_title", "")):
            continue
        overlap = len(q & _tokens(c.get("source_text", "")))
        if overlap:
            scored.append((overlap, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {"chunk_id": c["chunk_id"], "document_title": c["document_title"],
         "source_text": c["source_text"], "score": s}
        for s, c in scored[:k]
    ]


def apply_curation(rows: list[dict], corpus_index: dict, decisions: list[dict]) -> list[dict]:
    """Apply the decisions table to the clean rows.

    rows          : the full eval set (all namespaces), order preserved.
    corpus_index  : {chunk_id -> v3 chunk dict} for repoint lookups.
    decisions     : [{query, action: 'drop'|'repoint', new_chunk_id, reason}, ...]

    Returns a new list: dropped queries removed, repointed gold replaced from v3,
    every other row passed through unchanged. Raises KeyError if a repoint names a
    chunk_id absent from corpus_index.
    """
    by_query = {d["query"]: d for d in decisions}
    out = []
    for r in rows:
        d = by_query.get(r["query"])
        if d is None:
            out.append(r)
            continue
        if d["action"] == "drop":
            continue
        if d["action"] == "repoint":
            chunk = corpus_index[d["new_chunk_id"]]  # KeyError if unknown
            out.append({
                "query": r["query"],
                "namespace": r["namespace"],
                "chunk_id": chunk["chunk_id"],
                "chunk_text": chunk["source_text"],
                "document_title": chunk["document_title"],
            })
            continue
        raise ValueError(f"unknown action {d['action']!r} for query {r['query']!r}")
    return out
