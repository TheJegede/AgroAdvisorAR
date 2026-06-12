"""Zero-LLM-cost retrieval/generation failure split.

Reproduces the seed=7 answer-eval sample, runs retrieval ONLY (local gte-base
embed + Pinecone top-5, no generation, no judge), and joins the gold chunk
hit@5/rank against the correctness/faithfulness already scored in the L2 dump.

Failure taxonomy per item:
  OK                : corr >= 0.5 (not a failure)
  RETRIEVAL_MISS    : corr < 0.5 AND gold chunk NOT in top-5  -> retrieval/corpus lever
  GEN_SPECIFICITY   : corr < 0.5 AND gold in top-5 AND faith >= 0.5 -> generation lever (L3: quote exact rate)
  GEN_HALLUCINATION : corr < 0.5 AND gold in top-5 AND faith < 0.5  -> generation/guard lever

Heavy imports (pinecone, sentence-transformers, judge) are done inside
main() so the pure helpers below stay offline-testable.

Usage:
  cd <repo> && python -m evals.retrieval_precision \
      --eval-set evals/eval_set_v2.jsonl --sample 20 --seed 7 \
      --dump evals/_out_v3_L2on.jsonl --out evals/_retrieval_split.jsonl
"""
from __future__ import annotations


def rank_of(gold_id, ids):
    """1-based rank of gold_id in ids, or None if absent."""
    for i, x in enumerate(ids, 1):
        if x == gold_id:
            return i
    return None


def classify_failure(corr, faith, hit5):
    """Map a scored item to a failure-cause label. corr>=0.5 == pass == OK."""
    if corr >= 0.5:
        return "OK"
    if not hit5:
        return "RETRIEVAL_MISS"
    if faith >= 0.5:
        return "GEN_SPECIFICITY"
    return "GEN_HALLUCINATION"


def join_dump(query, dump):
    """Find the scored dump record for query (exact match), or None."""
    for r in dump:
        if r.get("query") == query:
            return r
    return None
