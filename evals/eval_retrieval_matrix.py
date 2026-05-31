"""Compare retrieval strategies on one eval set.

Runs dense-only, sparse-only, hybrid RRF, and optionally hybrid+rerank against
the same questions and prints one comparable table. This is Module 0 of the
retrieval-v3 plan: no production retrieval change should ship without this kind
of apples-to-apples evidence.

Example:
    EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2 \
      python evals/eval_retrieval_matrix.py --eval-set evals/eval_set_v2_remap.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

from hybrid_core import build_bm25, bm25_topk, rrf_fuse  # noqa: E402
from remap_eval_set import chunk_all_pdfs  # noqa: E402

MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME") or "agroar-prod-gte-v2"
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass(frozen=True)
class EvalItem:
    query: str
    namespace: str
    chunk_id: str


@dataclass(frozen=True)
class CorpusDoc:
    chunk_id: str
    namespace: str
    text: str


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


def summarize_rankings(
    items: list[EvalItem],
    rankings_by_strategy: dict[str, list[list[str]]],
    *,
    top_k: int,
    candidate_ks: tuple[int, ...],
) -> dict:
    """Aggregate retrieval metrics globally and by namespace."""
    by_strategy = {}
    for strategy, all_rankings in rankings_by_strategy.items():
        by_strategy[strategy] = _summarize_strategy(
            items, all_rankings, top_k=top_k, candidate_ks=candidate_ks,
        )
    return by_strategy


def _summarize_strategy(
    items: list[EvalItem],
    all_rankings: list[list[str]],
    *,
    top_k: int,
    candidate_ks: tuple[int, ...],
) -> dict:
    n = len(items)
    totals = _empty_totals(candidate_ks)
    by_ns: dict[str, dict] = defaultdict(lambda: _empty_totals(candidate_ks))

    for item, ranked_ids in zip(items, all_rankings):
        values = _item_metrics(ranked_ids, item.chunk_id, top_k, candidate_ks)
        _accumulate(totals, values)
        _accumulate(by_ns[item.namespace], values)

    return {
        **_finalize(totals, n, candidate_ks),
        "by_namespace": {
            ns: _finalize(vals, vals["count"], candidate_ks)
            for ns, vals in sorted(by_ns.items())
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


def _item_metrics(
    ranked_ids: list[str],
    gold_id: str,
    top_k: int,
    candidate_ks: tuple[int, ...],
) -> dict:
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
        out[f"candidate_recall_at_{k}"] = round(
            total[f"candidate_recall_at_{k}"] / n, 4
        )
    return out


def load_eval_items(path: Path) -> list[EvalItem]:
    return [
        EvalItem(
            query=row["query"],
            namespace=row["namespace"],
            chunk_id=row["chunk_id"],
        )
        for row in _read_jsonl(path)
    ]


def _read_jsonl(path: Path) -> Iterable[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def build_sparse_indexes(corpus_docs: list[CorpusDoc]) -> dict[str, object]:
    docs_by_ns: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for doc in corpus_docs:
        docs_by_ns[doc.namespace].append((doc.chunk_id, doc.text))
    return {ns: build_bm25(docs) for ns, docs in docs_by_ns.items()}


def load_corpus_docs() -> list[CorpusDoc]:
    docs = []
    for doc in chunk_all_pdfs():
        docs.append(
            CorpusDoc(
                chunk_id=doc.metadata["chunk_id"],
                namespace=doc.metadata["crop_type"],
                text=doc.page_content,
            )
        )
    return docs


def load_corpus_docs_jsonl(path: Path) -> list[CorpusDoc]:
    docs = []
    for row in _read_jsonl(path):
        docs.append(
            CorpusDoc(
                chunk_id=row["chunk_id"],
                namespace=row.get("namespace") or row.get("crop_type") or "general",
                text=row.get("retrieval_text") or row.get("source_text") or "",
            )
        )
    return docs


def dense_rankings(
    items: list[EvalItem],
    *,
    model_name: str,
    index_name: str,
    dense_k: int,
) -> list[list[str]]:
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(index_name)
    rankings = []
    for i, item in enumerate(items, start=1):
        vec = model.encode(item.query, normalize_embeddings=True).tolist()
        result = index.query(
            vector=vec,
            top_k=dense_k,
            namespace=item.namespace,
            include_values=False,
        )
        rankings.append([m["id"] for m in result.get("matches", [])])
        if i % 50 == 0:
            print(f"  dense {i}/{len(items)}")
    return rankings


def sparse_rankings(
    items: list[EvalItem],
    sparse_indexes: dict[str, object],
    *,
    sparse_k: int,
) -> list[list[str]]:
    rankings = []
    for item in items:
        bm25 = sparse_indexes.get(item.namespace)
        rankings.append(bm25_topk(bm25, item.query, sparse_k) if bm25 else [])
    return rankings


def hybrid_rankings(
    dense: list[list[str]],
    sparse: list[list[str]],
    *,
    rrf_k: int,
) -> list[list[str]]:
    return [rrf_fuse([d, s], k=rrf_k) for d, s in zip(dense, sparse)]


def rerank_rankings(
    items: list[EvalItem],
    rankings: list[list[str]],
    corpus_by_id: dict[str, CorpusDoc],
    *,
    model_name: str,
) -> list[list[str]]:
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name, max_length=512)
    reranked = []
    for i, (item, ranked_ids) in enumerate(zip(items, rankings), start=1):
        candidates = [rid for rid in ranked_ids if rid in corpus_by_id]
        missing = [rid for rid in ranked_ids if rid not in corpus_by_id]
        pairs = [(item.query, corpus_by_id[rid].text) for rid in candidates]
        if not pairs:
            reranked.append(ranked_ids)
            continue
        scores = model.predict(pairs)
        ordered = [
            rid
            for _score, rid in sorted(
                zip(scores, candidates), key=lambda score_id: score_id[0], reverse=True
            )
        ]
        # Keep the full candidate list after reranking so candidate_recall@20/30
        # remains a pre-final-context metric; hit@5/MRR@5 still judge the final top.
        reranked.append(ordered + missing)
        if i % 25 == 0:
            print(f"  rerank {i}/{len(items)}")
    return reranked


def print_table(summary: dict, *, top_k: int, candidate_ks: tuple[int, ...]) -> None:
    recall_cols = " ".join(f"rec@{k:02d}" for k in candidate_ks)
    print(f"\n=== RETRIEVAL MATRIX (top_k={top_k}) ===")
    print(f"{'strategy':>16} {'n':>4} {'hit@1':>7} {'hit@5':>7} {'MRR@5':>7} {'NDCG@5':>7} {recall_cols}")
    for name, vals in summary.items():
        recalls = " ".join(f"{vals[f'candidate_recall_at_{k}']:6.3f}" for k in candidate_ks)
        print(
            f"{name:>16} {vals['count']:4d} {vals['hit_at_1']:7.3f} "
            f"{vals['hit_at_k']:7.3f} {vals['mrr_at_k']:7.3f} "
            f"{vals['ndcg_at_k']:7.3f} {recalls}"
        )

    print("\n=== PER-NAMESPACE hit@5 / MRR@5 ===")
    for name, vals in summary.items():
        print(f"\n{name}:")
        for ns, ns_vals in vals["by_namespace"].items():
            print(
                f"  {ns:9} n={ns_vals['count']:3d} "
                f"hit@5={ns_vals['hit_at_k']:.3f} mrr@5={ns_vals['mrr_at_k']:.3f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path, default=Path(__file__).parent / "eval_set_v2.jsonl")
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--index", default=INDEX_NAME)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--dense-k", type=int, default=30)
    ap.add_argument("--sparse-k", type=int, default=30)
    ap.add_argument("--candidate-ks", default="20,30")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--rerank-model", default=os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"))
    ap.add_argument(
        "--corpus-jsonl",
        type=Path,
        default=None,
        help="Optional corpus artifact for sparse/rerank candidates, e.g. ingestion/en_chunks/corpus_v3.jsonl.",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    candidate_ks = tuple(int(k.strip()) for k in args.candidate_ks.split(",") if k.strip())
    fetch_k = max(args.dense_k, args.sparse_k, *candidate_ks, args.top_k)

    items = load_eval_items(args.eval_set)
    print(f"Items: {len(items)} | model: {args.model} | index: {args.index}")

    corpus_label = str(args.corpus_jsonl) if args.corpus_jsonl else "raw PDFs"
    print(f"Building sparse corpus from {corpus_label}...")
    corpus_docs = load_corpus_docs_jsonl(args.corpus_jsonl) if args.corpus_jsonl else load_corpus_docs()
    sparse_indexes = build_sparse_indexes(corpus_docs)
    corpus_by_id = {doc.chunk_id: doc for doc in corpus_docs}
    print(f"Sparse corpus: {len(corpus_docs)} chunks across {len(sparse_indexes)} namespaces")

    print("Running dense retrieval...")
    dense = dense_rankings(items, model_name=args.model, index_name=args.index, dense_k=fetch_k)
    sparse = sparse_rankings(items, sparse_indexes, sparse_k=fetch_k)
    hybrid = hybrid_rankings(dense, sparse, rrf_k=args.rrf_k)

    rankings = {
        "dense": dense,
        "sparse": sparse,
        "hybrid_rrf": hybrid,
    }
    if args.rerank:
        print(f"Reranking hybrid candidates with {args.rerank_model}...")
        rankings["hybrid_rerank"] = rerank_rankings(
            items, hybrid, corpus_by_id, model_name=args.rerank_model
        )

    summary = summarize_rankings(items, rankings, top_k=args.top_k, candidate_ks=candidate_ks)
    print_table(summary, top_k=args.top_k, candidate_ks=candidate_ks)

    out = args.out
    if out is None:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out = RESULTS_DIR / f"retrieval_matrix_{ts}.json"
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "eval_set": str(args.eval_set),
        "model": args.model,
        "index": args.index,
        "top_k": args.top_k,
        "dense_k": args.dense_k,
        "sparse_k": args.sparse_k,
        "candidate_ks": candidate_ks,
        "rerank": args.rerank,
        "summary": summary,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
