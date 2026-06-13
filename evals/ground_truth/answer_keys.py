"""OFFLINE answer-key store + synthesis/judge prompt-builders (eval-only).

Builds human-validated reference answers so correctness can be graded against
"any correct answer" instead of a single gold chunk. Fixes the single-gold
measurement artifact the rice curation surfaced (rice corr 10% / faith 86%).

NEVER imported by backend/rag.py or the request path.
"""
import json
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
CLEAN_SET = Path(__file__).parent.parent / "eval_set_v2_clean.jsonl"
ANSWER_KEYS = Path(__file__).parent / "answer_keys.jsonl"


def load_gold_by_query(rows: list[dict]) -> "OrderedDict[str, dict]":
    """Group gold rows by query -> {namespace, chunks:[{chunk_id, chunk_text}]}.

    Order preserved (first-seen). Multiple gold chunks per query are kept so
    synthesis can ground the reference answer in all of them.
    """
    by_q: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        q = r["query"]
        entry = by_q.setdefault(q, {"namespace": r.get("namespace"), "chunks": []})
        entry["chunks"].append(
            {"chunk_id": r.get("chunk_id"), "chunk_text": r.get("chunk_text", "")}
        )
    return by_q


def build_synthesis_prompt(query: str, entry: dict) -> str:
    """Prompt to synthesize a grounded reference answer from the gold chunks ONLY.

    Grounded (not free recall): the model may use only the provided passages, so
    a Gemini-distinct-from-generator judge does not leak outside knowledge.
    """
    passages = "\n\n".join(
        f"[chunk {i+1}] {c['chunk_text']}" for i, c in enumerate(entry["chunks"])
    )
    return (
        "You are building an answer key for an agricultural-advisory eval.\n"
        "Write the correct, concise reference answer to the farmer's question "
        "using ONLY the facts in the passages below. Do not add information not "
        "present in the passages. If the passages do not answer the question, "
        "reply exactly: INSUFFICIENT.\n\n"
        f"QUESTION: {query}\n\n"
        f"PASSAGES:\n{passages}\n\n"
        "REFERENCE ANSWER:"
    )


def parse_answer_key(query: str, namespace: str, source_chunk_ids: list[str],
                     raw_answer: str) -> dict | None:
    """Normalize one synthesized answer into an answer-key record.

    Returns None for an INSUFFICIENT / empty synthesis (those queries get no key
    and are skipped by the answerkey grader). validated defaults False.
    """
    text = (raw_answer or "").strip()
    if not text or text.upper().startswith("INSUFFICIENT"):
        return None
    return {
        "query": query,
        "namespace": namespace,
        "reference_answer": text,
        "source_chunk_ids": source_chunk_ids,
        "validated": False,
    }


def load_answer_keys(path=ANSWER_KEYS) -> dict:
    """Load answer_keys.jsonl into {query -> record}."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                out[rec["query"]] = rec
    return out


def write_answer_keys(records: list[dict], path=ANSWER_KEYS) -> None:
    """Write answer-key records (one JSON object per line)."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def validation_sample(records: list[dict], per_namespace: int = 5, seed: int = 7) -> list[dict]:
    """Deterministic stratified sample for the Task 5 human gate: up to
    per_namespace records per namespace."""
    import random
    by_ns: "OrderedDict[str, list]" = OrderedDict()
    for r in records:
        by_ns.setdefault(r.get("namespace"), []).append(r)
    rng = random.Random(seed)
    out = []
    for ns, recs in by_ns.items():
        picks = recs if len(recs) <= per_namespace else rng.sample(recs, per_namespace)
        out.extend(picks)
    return out
