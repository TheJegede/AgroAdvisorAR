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
import os, json, math, argparse, sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH", "thenlper/gte-base"
)
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
# `or` (not get-default): a present-but-empty env var (e.g. an unset GitHub
# secret injected as "") must still fall back, otherwise Pinecone .Index("")
# fails with the opaque "Either name or host must be specified".
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME") or "agroar-prod-gte-v2"

DEFAULT_EVAL_SET = Path(__file__).parent / "eval_set.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
TOP_K = 5

EVAL_WRITE_TO_DB = os.environ.get("EVAL_WRITE_TO_DB", "0") == "1"
RUN_ANSWER_EVAL = os.environ.get("RUN_ANSWER_EVAL", "0") == "1"
ANSWER_EVAL_SAMPLE = int(os.environ.get("ANSWER_EVAL_SAMPLE", "20"))
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
EVAL_FAIL_CI_ON_STATUS = {
    s.strip()
    for s in os.environ.get("EVAL_FAIL_CI_ON_STATUS", "failed").split(",")
    if s.strip()
}

_supabase_client = None

def _get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_client


def _fetch_confidence_mean() -> float | None:
    """Query recent chat_messages for mean confidence_score. Returns None if unavailable."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        return None
    try:
        client = _get_supabase_client()
        rows = (
            client.table("chat_messages")
            .select("confidence_score")
            .not_.is_("confidence_score", "null")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        scores = [r["confidence_score"] for r in (rows.data or []) if r.get("confidence_score") is not None]
        return round(sum(scores) / len(scores), 4) if scores else None
    except Exception as e:
        print(f"Confidence mean fetch failed: {e}")
        return None


def _maybe_run_answer_eval(eval_set_path: Path) -> tuple[float | None, str, str | None]:
    """Optionally run LLM-as-judge answer correctness eval."""
    if not RUN_ANSWER_EVAL:
        return None, "not_run", None
    try:
        import asyncio
        from answer_eval import score_corpus
        print(f"\nRunning answer eval on {ANSWER_EVAL_SAMPLE} sampled items...")
        result = asyncio.run(score_corpus(
            eval_set_path=eval_set_path,
            sample_size=ANSWER_EVAL_SAMPLE,
            verbose=True,
        ))
        print(f"\nAnswer eval: {result}")
        return result["answer_correct_pct"], "ok", None
    except Exception as e:
        print(f"Answer eval failed: {e}")
        return None, "failed", str(e)


def _write_to_supabase(summary: dict, answer_pct: float | None) -> None:
    """Insert an eval_runs row. Silent no-op if Supabase env vars missing."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        print("Skipping Supabase write — SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        return
    try:
        client = _get_supabase_client()
        client.table("eval_runs").insert({
            "mrr_at_5": summary["mrr_at_5"],
            "ndcg_at_5": summary["ndcg_at_5"],
            "answer_correct_pct": answer_pct,
            "total_items": summary["n_items"],
            "model_version": summary["model"],
            "retrieval_status": summary["retrieval_status"],
            "answer_status": summary["answer_status"],
            "run_status": summary["run_status"],
            "error_message": summary.get("error_message"),
            "answer_confidence_mean": summary.get("answer_confidence_mean"),
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
    items = [json.loads(l) for l in open(eval_set_path, encoding="utf-8")]
    print(f"Eval items:      {len(items)}")
    print(f"Embedding model: {EMBEDDING_MODEL_PATH}")
    print(f"Pinecone index:  {PINECONE_INDEX_NAME}")

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
        "retrieval_status": "ok",
        "answer_status": "not_run",
        "run_status": "ok",
        "error_message": None,
    }

    answer_pct, answer_status, answer_error = _maybe_run_answer_eval(eval_set_path)
    summary["answer_status"] = answer_status
    if answer_pct is not None:
        summary["answer_correct_pct"] = answer_pct
    if answer_error:
        summary["error_message"] = answer_error

    # Fetch answer confidence mean from recent chat_messages
    conf_mean = _fetch_confidence_mean()
    if conf_mean is not None:
        summary["answer_confidence_mean"] = conf_mean

    if summary["retrieval_status"] == "failed":
        summary["run_status"] = "failed"
    elif answer_status == "failed":
        summary["run_status"] = "partial"

    print("\n=== EVAL RESULTS ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"eval_{ts}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved -> {out}")

    if EVAL_WRITE_TO_DB:
        _write_to_supabase(summary, answer_pct)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET,
                        help="Path to eval_set.jsonl (default: evals/eval_set.jsonl)")
    args = parser.parse_args()
    try:
        eval_summary = run_eval(args.eval_set)
    except Exception as e:
        eval_summary = {
            "model": EMBEDDING_MODEL_PATH,
            "timestamp": datetime.utcnow().isoformat(),
            "n_items": 0,
            "mrr_at_5": None,
            "ndcg_at_5": None,
            "hit_at_1": None,
            "hit_at_5": None,
            "retrieval_status": "failed",
            "answer_status": "not_run",
            "run_status": "failed",
            "error_message": str(e),
        }
        print(f"Eval failed: {e}")
        if EVAL_WRITE_TO_DB:
            _write_to_supabase(eval_summary, None)

    if eval_summary["run_status"] in EVAL_FAIL_CI_ON_STATUS:
        sys.exit(1)
