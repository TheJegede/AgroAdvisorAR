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
