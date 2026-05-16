"""
MRR@5 + NDCG@5 eval runner.

Embeds each query with the current embedding model (EMBEDDING_MODEL_PATH env var),
queries Pinecone top-5, computes retrieval metrics. Saves results to evals/results/.

Run: python evals/eval_runner.py
     python evals/eval_runner.py --eval-set evals/eval_set_v2.jsonl
To test fine-tuned model: set EMBEDDING_MODEL_PATH=./models/agroar-embeddings-v2 first.

Supabase logging: set EVAL_WRITE_TO_DB=1 (CI default) to append a row to
the eval_runs table. Local CLI runs default to off so they don't pollute the
dashboard with experiments.
"""
import os, json, math, argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2"
)
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")

DEFAULT_EVAL_SET = Path(__file__).parent / "eval_set.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
TOP_K = 5

EVAL_WRITE_TO_DB = os.environ.get("EVAL_WRITE_TO_DB", "0") == "1"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")


def _write_to_supabase(summary: dict) -> None:
    """Insert an eval_runs row. Silent no-op if Supabase env vars missing."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        print("Skipping Supabase write — SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        return
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        client.table("eval_runs").insert({
            "mrr_at_5": summary["mrr_at_5"],
            "ndcg_at_5": summary["ndcg_at_5"],
            "answer_correct_pct": None,
            "total_items": summary["n_items"],
            "model_version": summary["model"],
        }).execute()
        print("Wrote eval_runs row to Supabase")
    except Exception as e:
        print(f"Supabase write failed: {e}")


def _mrr(retrieved: list[str], relevant: str, k: int = 5) -> float:
    for rank, rid in enumerate(retrieved[:k], start=1):
        if rid == relevant:
            return 1.0 / rank
    return 0.0


def _ndcg(retrieved: list[str], relevant: str, k: int = 5) -> float:
    for rank, rid in enumerate(retrieved[:k], start=1):
        if rid == relevant:
            return 1.0 / math.log2(rank + 1)
    return 0.0


def run_eval(eval_set_path: Path = DEFAULT_EVAL_SET) -> dict:
    items = [json.loads(l) for l in open(eval_set_path)]
    print(f"Eval items:      {len(items)}")
    print(f"Embedding model: {EMBEDDING_MODEL_PATH}")

    model = SentenceTransformer(EMBEDDING_MODEL_PATH)
    index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)

    mrr_scores, ndcg_scores = [], []
    hits1, hits5 = 0, 0

    for i, item in enumerate(items):
        vec = model.encode(item["query"], normalize_embeddings=True).tolist()
        result = index.query(
            vector=vec,
            top_k=TOP_K,
            namespace=item["namespace"],
            include_values=False,
        )
        ids = [m["id"] for m in result.get("matches", [])]
        mrr_scores.append(_mrr(ids, item["chunk_id"]))
        ndcg_scores.append(_ndcg(ids, item["chunk_id"]))
        if ids and ids[0] == item["chunk_id"]:
            hits1 += 1
        if item["chunk_id"] in ids:
            hits5 += 1

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(items)} evaluated")

    n = len(items)
    summary = {
        "model": EMBEDDING_MODEL_PATH,
        "timestamp": datetime.utcnow().isoformat(),
        "n_items": n,
        "mrr_at_5": round(sum(mrr_scores) / n, 4),
        "ndcg_at_5": round(sum(ndcg_scores) / n, 4),
        "hit_at_1": round(hits1 / n, 4),
        "hit_at_5": round(hits5 / n, 4),
    }

    print("\n=== EVAL RESULTS ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"eval_{ts}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved -> {out}")

    if EVAL_WRITE_TO_DB:
        _write_to_supabase(summary)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET,
                        help="Path to eval_set.jsonl (default: evals/eval_set.jsonl)")
    args = parser.parse_args()
    run_eval(args.eval_set)
