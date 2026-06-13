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
