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


def write_audit(rows: list[dict], corpus_index: dict, decisions: list[dict]) -> str:
    """Render a markdown audit table: one row per decision.

    Columns: query | action | old_gold_title | new_gold_title | new_chunk_id | reason.
    """
    by_query = {r["query"]: r for r in rows}
    lines = [
        "# Rice Gold Curation — Audit",
        "",
        "Review each row. For a wrong re-point, edit the corresponding entry in",
        "`evals/rice_curation_decisions.json` (change `new_chunk_id` or set",
        "`action` to `drop`), then re-run Task 7.",
        "",
        "| query | action | old gold title | new gold title | new chunk_id | reason |",
        "|---|---|---|---|---|---|",
    ]
    for d in decisions:
        old_row = by_query.get(d["query"], {})
        old_title = old_row.get("document_title", "?")
        if d["action"] == "repoint":
            chunk = corpus_index.get(d["new_chunk_id"], {})
            new_title = chunk.get("document_title", "?")
        else:
            new_title = "—"
        q = d["query"].replace("|", "\\|")
        lines.append(
            f"| {q[:70]} | {d['action']} | {old_title[:50]} | {new_title[:50]} "
            f"| {d.get('new_chunk_id') or '—'} | {d.get('reason','')[:60]} |"
        )
    return "\n".join(lines) + "\n"


DECISIONS_PATH = Path(__file__).parent / "rice_curation_decisions.json"
AUDIT_PATH = REPO_ROOT / "docs" / "superpowers" / "2026-06-12-rice-gold-curation-audit.md"

# Wrong-crop items to DROP outright (substring-matched against the query so we
# don't depend on exact wording). From the rice diagnosis EVAL_MISLABEL bucket:
# cross-crop (corn/soybean/wheat) questions mis-filed in the rice namespace.
# Task 6 human review (Taiwo, 2026-06-13) confirmed all 7 should drop, not repoint.
_DROP_SUBSTRINGS = [
    "planting soybeans later than usual",        # soybean-variety question
    "corn's been lookin",                        # corn-nitrogen question
    "lower corn yields",                         # corn-potassium question
    "my soybean yields are down",                # soybean-variety question
    "different prices for my soybeans",          # soybean-grading question
    "my wheat's been fallin' over in the rain",  # wheat-lodging question
    "which wheat varieties are less likely to fall over",  # wheat-lodging question
]


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_draft_decisions(rows: list[dict], corpus: list[dict]) -> list[dict]:
    """Deterministic draft: drop known wrong-crop items, repoint each flagged
    yearly-volume row to its top keyword candidate. Human-reviewed in Task 6."""
    decisions = []
    flagged = flag_yearly_volume_gold(rows)
    flagged_queries = {r["query"] for r in flagged}
    for r in rows:
        if r["query"] not in flagged_queries:
            continue
        if any(s in r["query"].lower() for s in _DROP_SUBSTRINGS):
            decisions.append({"query": r["query"], "action": "drop",
                              "new_chunk_id": None, "reason": "wrong-crop (soybean) in rice namespace"})
            continue
        cands = candidate_chunks(r["query"], corpus, k=5)
        if not cands:
            decisions.append({"query": r["query"], "action": "drop",
                              "new_chunk_id": None, "reason": "no topical rice candidate found"})
            continue
        top = cands[0]
        decisions.append({"query": r["query"], "action": "repoint",
                          "new_chunk_id": top["chunk_id"],
                          "reason": f"keyword top-1: {top['document_title'][:40]} (score {top['score']})"})
    return decisions


def main():
    rows = _load_jsonl(CLEAN_SET)
    corpus = load_corpus_v3()
    corpus_index = {c["chunk_id"]: c for c in corpus}
    decisions = build_draft_decisions(rows, corpus)
    with open(DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2)
    audit = write_audit(rows, corpus_index, decisions)
    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        f.write(audit)
    n_drop = sum(1 for d in decisions if d["action"] == "drop")
    n_repoint = sum(1 for d in decisions if d["action"] == "repoint")
    print(f"draft decisions: {len(decisions)} ({n_repoint} repoint, {n_drop} drop)")
    print(f"  -> {DECISIONS_PATH}")
    print(f"  -> {AUDIT_PATH}")


if __name__ == "__main__":
    main()
