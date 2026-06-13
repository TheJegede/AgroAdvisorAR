"""Standalone OFFLINE RAGAS diagnostic eval.

Completes the retrieval x generation measurement matrix on the held-out set:
  faithfulness, answer_relevancy        (generation, reference-free)
  context_precision (reference-free)    (retrieval)
  context_recall (gold-chunk reference) (retrieval; rice = provisional)

Consumes a capture-enabled dump from answer_eval_full.py (--dump, with `answer`
+ `contexts`) and joins gold chunk_text from eval_set_v2_clean.jsonl as
reference_contexts. EVAL-ONLY: never imported by rag.py / the request path.

Run (cost-incurring — see cost gate in main()):
  python evals/ragas_eval.py --dump evals/_capture_b1on.jsonl
"""
import json
from collections import defaultdict
from pathlib import Path


def load_dump(path) -> list[dict]:
    """Read the capture-enabled answer_eval_full dump (one JSON object/line)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_gold_reference_contexts(eval_set_path) -> dict:
    """Map query -> [gold chunk_text, ...] from eval_set_v2_clean.jsonl.

    The clean eval set is a *retrieval* gold (query, chunk_id, chunk_text,
    document_title, namespace) with possibly multiple gold chunks per query.
    These serve as RAGAS `reference_contexts` for NonLLMContextRecall.
    """
    out = defaultdict(list)
    with open(eval_set_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            text = row.get("chunk_text")
            if text:
                out[row["query"]].append(text)
    return dict(out)
