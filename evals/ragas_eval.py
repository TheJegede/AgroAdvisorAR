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


from ragas import SingleTurnSample


def build_samples(dump_records: list[dict], gold_map: dict) -> tuple[list, list]:
    """Build (SingleTurnSamples, metadata) aligned by index.

    metadata[i] = {"namespace", "suppressed"} for per-crop / per-suppressed
    aggregation, since RAGAS results don't carry our domain fields.
    """
    samples, meta = [], []
    for r in dump_records:
        samples.append(SingleTurnSample(
            user_input=r["query"],
            response=r.get("answer") or "",
            retrieved_contexts=list(r.get("contexts") or []),
            reference_contexts=list(gold_map.get(r["query"], [])),
        ))
        meta.append({
            "namespace": r.get("namespace"),
            "suppressed": bool(r.get("suppressed")),
        })
    return samples, meta


# Reference-based metric(s) whose rice numbers are provisional until Phase 2
# (rice gold labels are contaminated — see spec §3).
_PROVISIONAL_FOR_RICE = {"non_llm_context_recall"}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _summarize_group(rows: list[dict], metric_keys: list[str], crop=None) -> dict:
    out = {"count": len(rows)}
    for k in metric_keys:
        out[k] = _mean([r.get(k) for r in rows])
    if crop is not None:
        for k in _PROVISIONAL_FOR_RICE:
            out[f"{k}_provisional"] = (crop == "rice")
    return out


def aggregate_scores(rows: list[dict], metric_keys: list[str]) -> dict:
    """Group per-row RAGAS scores into a report: overall, per-crop (namespace),
    and per-suppressed-flag. Rice reference-based cells marked provisional."""
    by_crop = defaultdict(list)
    by_supp = defaultdict(list)
    for r in rows:
        by_crop[r.get("namespace")].append(r)
        by_supp[bool(r.get("suppressed"))].append(r)

    return {
        "overall": _summarize_group(rows, metric_keys),
        "by_crop": {c: _summarize_group(g, metric_keys, crop=c)
                    for c, g in sorted(by_crop.items(), key=lambda kv: str(kv[0]))},
        "by_suppressed": {s: _summarize_group(g, metric_keys)
                          for s, g in by_supp.items()},
    }


def _fmt(x):
    return " n/a" if x is None else f"{x:.2f}"


def format_report(report: dict, metric_keys: list[str]) -> str:
    lines = []
    header = f"{'group':>20} {'n':>3} " + " ".join(f"{k[:14]:>14}" for k in metric_keys)

    def row(label, d):
        cells = []
        for k in metric_keys:
            val = _fmt(d.get(k))
            if d.get(f"{k}_provisional"):
                val += "*"
            cells.append(f"{val:>14}")
        lines.append(f"{label:>20} {d.get('count', 0):>3} " + " ".join(cells))

    lines.append("=== RAGAS DIAGNOSTIC MATRIX ===")
    lines.append(header)
    row("OVERALL", report["overall"])
    lines.append("--- by crop ---")
    for crop, d in report["by_crop"].items():
        row(str(crop), d)
    lines.append("--- by suppressed ---")
    for flag, d in report["by_suppressed"].items():
        row(f"suppressed={flag}", d)
    lines.append("* = provisional (contaminated rice gold; fixed in Phase 2)")
    return "\n".join(lines)


import argparse
import os
import sys

# Make backend importable for the local gte embedder.
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def _build_llm_and_embeddings():
    """Gemini-2.5-flash judge + local gte embedder, wrapped for RAGAS."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from services.embedding import MiniLMEmbeddings  # local gte, $0

    judge = ChatGoogleGenerativeAI(
        model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )
    return (LangchainLLMWrapper(judge),
            LangchainEmbeddingsWrapper(MiniLMEmbeddings()))


def run(dump_path, eval_set_path):
    """Score a capture-enabled dump with the 4-metric matrix. Spends Gemini tokens."""
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import (
        Faithfulness, ResponseRelevancy,
        LLMContextPrecisionWithoutReference, NonLLMContextRecall,
    )

    dump = load_dump(dump_path)
    gold = load_gold_reference_contexts(eval_set_path)
    samples, meta = build_samples(dump, gold)

    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithoutReference(),
        NonLLMContextRecall(),
    ]
    metric_keys = [m.name for m in metrics]

    llm, embeddings = _build_llm_and_embeddings()
    result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )

    df = result.to_pandas()
    rows = []
    for i, m in enumerate(meta):
        row = {"namespace": m["namespace"], "suppressed": m["suppressed"]}
        for k in metric_keys:
            val = df[k].iloc[i] if k in df.columns else None
            # RAGAS uses NaN for unscored cells; normalize to None.
            row[k] = None if val is None or (isinstance(val, float) and val != val) else float(val)
        rows.append(row)

    report = aggregate_scores(rows, metric_keys)
    print(format_report(report, metric_keys))
    return report


_COST_NOTE = """\
COST GATE — this run spends Gemini-2.5-flash tokens.
Estimate: ~n items x (faithfulness ~2 calls + answer_relevancy ~1 + context_precision
~1/retrieved-context). For n=40 with ~5 contexts/item this is on the order of a few
hundred gemini-2.5-flash calls (cheap, but non-zero). NonLLMContextRecall uses string
similarity only ($0). Embeddings are local gte ($0).
Re-run with --confirm-cost to proceed."""


def main():
    ap = argparse.ArgumentParser(description="Offline RAGAS diagnostic eval.")
    ap.add_argument("--dump", type=Path, required=True,
                    help="capture-enabled dump from answer_eval_full.py --dump")
    ap.add_argument("--eval-set", type=Path,
                    default=Path(__file__).parent / "eval_set_v2_clean.jsonl",
                    help="gold retrieval set (reference_contexts for context_recall)")
    ap.add_argument("--confirm-cost", action="store_true",
                    help="acknowledge token cost and run (otherwise prints estimate and exits)")
    args = ap.parse_args()

    if not args.confirm_cost:
        print(_COST_NOTE)
        raise SystemExit(0)

    run(args.dump, args.eval_set)


if __name__ == "__main__":
    main()
