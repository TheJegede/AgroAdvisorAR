"""End-to-end answer-correctness eval.

For each sampled eval item:
  1. Runs the production RAG chain (`backend.services.rag.run_rag_query`)
  2. Judges the advisory against the gold chunk via `evals.judge.score_item`

Returns the average score × 100 as `answer_correct_pct` suitable for
`eval_runs.answer_correct_pct` (numeric(4,1)).

Run standalone for ad-hoc analysis:
    GROQ_API_KEY=... python evals/answer_eval.py --sample 20

Or import `score_corpus` from `eval_runner.py` when `RUN_ANSWER_EVAL=1`.
"""
import sys
import os
import json
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Backend services live in a sibling package, not on the import path by default.
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.rag import run_rag_query  # noqa: E402
from judge import score_item, sample_items  # noqa: E402

DEFAULT_EVAL_SET = Path(__file__).parent / "eval_set_v2.jsonl"
# Use a real Arkansas county FIPS; SSURGO + NOAA injection should succeed.
EVAL_COUNTY_FIPS = "05031"  # Craighead County


# Map eval-set namespace → classifier category that triggers the same namespace.
_NAMESPACE_TO_CATEGORY = {
    "rice": "IN_SCOPE_RICE",
    "soybeans": "IN_SCOPE_SOYBEANS",
    "poultry": "IN_SCOPE_POULTRY",
    "general": "IN_SCOPE_GENERAL_AG",
}


async def _evaluate(item: dict) -> tuple[float, str]:
    category = _NAMESPACE_TO_CATEGORY.get(item["namespace"], "IN_SCOPE_GENERAL_AG")
    advisory = await run_rag_query(
        message=item["query"],
        county_fips=EVAL_COUNTY_FIPS,
        language="en",
        category=category,
        session_history=[],
    )
    # run_rag_query now returns (advisory, retrieved_chunks)
    if isinstance(advisory, tuple):
        advisory = advisory[0]
    advisory_dict = advisory.model_dump() if hasattr(advisory, "model_dump") else advisory
    score, rationale = score_item(item["query"], advisory_dict, item["chunk_text"])
    return score, rationale


async def score_corpus(
    eval_set_path: Path = DEFAULT_EVAL_SET,
    sample_size: int = 20,
    seed: int = 7,
    verbose: bool = False,
) -> dict:
    items = [json.loads(l) for l in open(eval_set_path)]
    sampled = sample_items(items, sample_size, seed=seed)

    scores: list[float] = []
    skipped = 0
    for i, item in enumerate(sampled, 1):
        try:
            score, rationale = await _evaluate(item)
            scores.append(score)
            if verbose:
                print(f"  [{i}/{len(sampled)}] score={score:.2f} — {rationale[:80]}")
        except Exception as e:
            skipped += 1
            if verbose:
                print(f"  [{i}/{len(sampled)}] SKIPPED — {type(e).__name__}: {e}")

    if not scores:
        return {"answer_correct_pct": None, "scored": 0, "skipped": skipped}

    pct = round(100.0 * sum(scores) / len(scores), 1)
    return {
        "answer_correct_pct": pct,
        "scored": len(scores),
        "skipped": skipped,
        "sample_size": sample_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    result = asyncio.run(score_corpus(
        eval_set_path=args.eval_set,
        sample_size=args.sample,
        seed=args.seed,
        verbose=True,
    ))
    print("\n=== ANSWER EVAL ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
