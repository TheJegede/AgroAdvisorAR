"""Spike: measure dense-only vs hybrid (BM25+dense+RRF) retrieval on the same
queries, same index, in one pass. Proves whether hybrid is worth integrating
into the backend before touching the prod query path.

Run: EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2 \
       python evals/eval_hybrid.py --eval-set evals/eval_set_v2_remap.jsonl
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from remap_eval_set import chunk_all_pdfs
from hybrid_core import build_bm25, bm25_topk, rrf_fuse

MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "thenlper/gte-base")
INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod-gte-v2")
DENSE_K = 20
SPARSE_K = 20
TOP_K = 5


def _metrics(ranked_ids, gold, k=TOP_K):
    hit1 = 1.0 if ranked_ids[:1] == [gold] else 0.0
    hit5 = 1.0 if gold in ranked_ids[:k] else 0.0
    mrr = 0.0
    for rank, rid in enumerate(ranked_ids[:k], start=1):
        if rid == gold:
            mrr = 1.0 / rank
            break
    return hit1, hit5, mrr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path,
                    default=Path(__file__).parent / "eval_set_v2_remap.jsonl")
    args = ap.parse_args()

    with args.eval_set.open(encoding="utf-8") as f:
        items = [json.loads(l) for l in f]
    print(f"Items: {len(items)} | model: {MODEL_NAME} | index: {INDEX_NAME}")

    print("Re-chunking PDFs for BM25 corpus...")
    docs = chunk_all_pdfs()
    by_ns = defaultdict(list)
    for d in docs:
        by_ns[d.metadata["crop_type"]].append((d.metadata["chunk_id"], d.page_content))
    bm25_by_ns = {ns: build_bm25(lst) for ns, lst in by_ns.items()}
    print(f"BM25 built over {len(docs)} chunks across {len(bm25_by_ns)} namespaces.")

    model = SentenceTransformer(MODEL_NAME)
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(INDEX_NAME)

    agg = {"dense": [0.0, 0.0, 0.0], "hybrid": [0.0, 0.0, 0.0]}
    # Diagnostics: recall@20 for each retriever + their union (the ceiling a
    # reranker over the candidate pool could reach), and BM25's UNIQUE rescues
    # (gold found by BM25@20 that dense@20 missed).
    diag = {"dense@20": 0, "sparse@20": 0, "union@20": 0, "bm25_unique_rescue": 0}
    n = len(items)
    for i, it in enumerate(items):
        q, ns, gold = it["query"], it["namespace"], it["chunk_id"]
        emb = model.encode(q, normalize_embeddings=True).tolist()
        res = index.query(vector=emb, top_k=DENSE_K, namespace=ns, include_values=False)
        dense_ids = [m["id"] for m in res.get("matches", [])]
        sparse_ids = bm25_topk(bm25_by_ns[ns], q, SPARSE_K) if ns in bm25_by_ns else []
        fused = rrf_fuse([dense_ids, sparse_ids])

        for name, ids in (("dense", dense_ids), ("hybrid", fused)):
            h1, h5, mrr = _metrics(ids, gold)
            agg[name][0] += h1
            agg[name][1] += h5
            agg[name][2] += mrr

        in_dense = gold in dense_ids
        in_sparse = gold in sparse_ids
        diag["dense@20"] += int(in_dense)
        diag["sparse@20"] += int(in_sparse)
        diag["union@20"] += int(in_dense or in_sparse)
        diag["bm25_unique_rescue"] += int(in_sparse and not in_dense)

        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{n}")

    print("\n=== DENSE-ONLY vs HYBRID (BM25+dense+RRF), same queries ===")
    print(f"{'':10} {'hit@1':>8} {'hit@5':>8} {'MRR@5':>8}")
    for name in ("dense", "hybrid"):
        h1, h5, mrr = (v / n for v in agg[name])
        print(f"{name:10} {h1:8.3f} {h5:8.3f} {mrr:8.3f}")

    print("\n=== RECALL DIAGNOSTICS (gold in top-20) ===")
    for key in ("dense@20", "sparse@20", "union@20", "bm25_unique_rescue"):
        print(f"  {key:20} {diag[key]/n:6.3f}  ({diag[key]}/{n})")


if __name__ == "__main__":
    main()
