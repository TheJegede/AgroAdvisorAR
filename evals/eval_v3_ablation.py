"""Run local dense retrieval ablations over corpus_v3.

This compares text representations without creating new Pinecone indexes:

- source_text: original chunk only
- title_section_source: document title + section + original chunk
- retrieval_text: current contextual header + original chunk

It is intentionally local and deterministic so Module 2 changes can be judged
before another hosted index is built.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

RESULTS_DIR = Path(__file__).parent / "results"


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def text_for_variant(row: dict, variant: str) -> str:
    source = row.get("source_text") or ""
    if variant == "source_text":
        return source
    if variant == "title_section_source":
        parts = [row.get("document_title") or ""]
        if row.get("section_heading"):
            parts.append(row["section_heading"])
        return " | ".join(part for part in parts if part) + "\n\n" + source
    if variant == "retrieval_text":
        return row.get("retrieval_text") or source
    raise ValueError(f"Unknown variant: {variant}")


def reciprocal_rank(ranked_ids: list[str], gold_id: str, k: int) -> float:
    for rank, candidate_id in enumerate(ranked_ids[:k], start=1):
        if candidate_id == gold_id:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: list[str], gold_id: str, k: int) -> float:
    for rank, candidate_id in enumerate(ranked_ids[:k], start=1):
        if candidate_id == gold_id:
            return 1.0 / math.log2(rank + 1)
    return 0.0


def summarize(items: list[dict], rankings: list[list[str]], *, top_k: int, candidate_ks: tuple[int, ...]) -> dict:
    totals = _empty_totals(candidate_ks)
    by_ns: dict[str, dict] = defaultdict(lambda: _empty_totals(candidate_ks))
    for item, ranked_ids in zip(items, rankings):
        values = _item_metrics(ranked_ids, item["chunk_id"], top_k, candidate_ks)
        _accumulate(totals, values)
        _accumulate(by_ns[item["namespace"]], values)
    return {
        **_finalize(totals, len(items), candidate_ks),
        "by_namespace": {
            namespace: _finalize(values, values["count"], candidate_ks)
            for namespace, values in sorted(by_ns.items())
        },
    }


def _empty_totals(candidate_ks: tuple[int, ...]) -> dict:
    totals = {
        "count": 0,
        "hit_at_1": 0.0,
        "hit_at_k": 0.0,
        "mrr_at_k": 0.0,
        "ndcg_at_k": 0.0,
    }
    for k in candidate_ks:
        totals[f"candidate_recall_at_{k}"] = 0.0
    return totals


def _item_metrics(ranked_ids: list[str], gold_id: str, top_k: int, candidate_ks: tuple[int, ...]) -> dict:
    values = {
        "count": 1,
        "hit_at_1": float(ranked_ids[:1] == [gold_id]),
        "hit_at_k": float(gold_id in ranked_ids[:top_k]),
        "mrr_at_k": reciprocal_rank(ranked_ids, gold_id, top_k),
        "ndcg_at_k": ndcg_at_k(ranked_ids, gold_id, top_k),
    }
    for k in candidate_ks:
        values[f"candidate_recall_at_{k}"] = float(gold_id in ranked_ids[:k])
    return values


def _accumulate(total: dict, values: dict) -> None:
    for key, value in values.items():
        total[key] += value


def _finalize(total: dict, n: int, candidate_ks: tuple[int, ...]) -> dict:
    if n == 0:
        return {}
    out = {
        "count": n,
        "hit_at_1": round(total["hit_at_1"] / n, 4),
        "hit_at_k": round(total["hit_at_k"] / n, 4),
        "mrr_at_k": round(total["mrr_at_k"] / n, 4),
        "ndcg_at_k": round(total["ndcg_at_k"] / n, 4),
    }
    for k in candidate_ks:
        out[f"candidate_recall_at_{k}"] = round(total[f"candidate_recall_at_{k}"] / n, 4)
    return out


def rank_variant(
    *,
    model,
    corpus_rows: list[dict],
    eval_items: list[dict],
    variant: str,
    fetch_k: int,
    batch_size: int,
) -> list[list[str]]:
    by_ns: dict[str, list[dict]] = defaultdict(list)
    for row in corpus_rows:
        by_ns[row.get("namespace") or row.get("crop_type") or "general"].append(row)

    encoded_by_ns = {}
    for namespace, rows in sorted(by_ns.items()):
        texts = [text_for_variant(row, variant) for row in rows]
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=True,
        )
        encoded_by_ns[namespace] = {
            "ids": [row["chunk_id"] for row in rows],
            "embeddings": np.asarray(embeddings, dtype=np.float32),
        }

    rankings = []
    query_embeddings = model.encode(
        [item["query"] for item in eval_items],
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=True,
    )
    for item, query_embedding in zip(eval_items, np.asarray(query_embeddings, dtype=np.float32)):
        namespace_data = encoded_by_ns.get(item["namespace"])
        if not namespace_data:
            rankings.append([])
            continue
        scores = namespace_data["embeddings"] @ query_embedding
        top_idx = np.argpartition(-scores, min(fetch_k, len(scores) - 1))[:fetch_k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        rankings.append([namespace_data["ids"][i] for i in top_idx])
    return rankings


def print_table(summary: dict) -> None:
    print("\n=== V3 ABLATION ===")
    print(f"{'variant':>22} {'n':>4} {'hit@1':>7} {'hit@5':>7} {'MRR@5':>7} {'NDCG@5':>7} {'rec@20':>7} {'rec@30':>7}")
    for variant, values in summary.items():
        print(
            f"{variant:>22} {values['count']:4d} {values['hit_at_1']:7.3f} "
            f"{values['hit_at_k']:7.3f} {values['mrr_at_k']:7.3f} "
            f"{values['ndcg_at_k']:7.3f} {values['candidate_recall_at_20']:7.3f} "
            f"{values['candidate_recall_at_30']:7.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--corpus-jsonl", type=Path, required=True)
    parser.add_argument("--model", default="thenlper/gte-base")
    parser.add_argument("--variants", default="source_text,title_section_source,retrieval_text")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-ks", default="20,30")
    parser.add_argument("--fetch-k", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    candidate_ks = tuple(int(k.strip()) for k in args.candidate_ks.split(",") if k.strip())
    fetch_k = max(args.fetch_k, args.top_k, *candidate_ks)
    variants = [variant.strip() for variant in args.variants.split(",") if variant.strip()]
    corpus_rows = read_jsonl(args.corpus_jsonl)
    eval_items = read_jsonl(args.eval_set)

    print(f"Items: {len(eval_items)} | corpus: {len(corpus_rows)} | model: {args.model}")
    model = SentenceTransformer(args.model)

    summary = {}
    for variant in variants:
        print(f"\nRunning variant: {variant}")
        rankings = rank_variant(
            model=model,
            corpus_rows=corpus_rows,
            eval_items=eval_items,
            variant=variant,
            fetch_k=fetch_k,
            batch_size=args.batch_size,
        )
        summary[variant] = summarize(
            eval_items,
            rankings,
            top_k=args.top_k,
            candidate_ks=candidate_ks,
        )

    print_table(summary)

    out = args.out
    if out is None:
        RESULTS_DIR.mkdir(exist_ok=True)
        out = RESULTS_DIR / f"v3_ablation_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "eval_set": str(args.eval_set),
        "corpus_jsonl": str(args.corpus_jsonl),
        "model": args.model,
        "variants": variants,
        "summary": summary,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
