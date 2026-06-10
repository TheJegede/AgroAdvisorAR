# evals/diagnostic/runner.py
"""D3 gate: classify a human gold-labeled sample and emit the split report.

The report layer (`build_report`) is pure over already-classified items, so it
is unit-tested. `run_diagnostic` does the live RAG + judge I/O and is run
manually against the real sample.
"""
import sys
import json
import asyncio
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from evals.diagnostic.gold_schema import load_gold_records, GoldRecord
from evals.diagnostic.buckets import Bucket, classify, JudgeResult
from evals.diagnostic.span_verify import fact_retrieved
from evals.diagnostic.pipeline_flags import is_abstention
from evals.diagnostic.containment_judge import judge_containment
from evals.diagnostic.conditional_judge import (
    judge_conditional, flatten_advisory, CompletenessResult,
)

_NAMESPACE_TO_CATEGORY = {
    "rice": "IN_SCOPE_RICE",
    "soybeans": "IN_SCOPE_SOYBEANS",
    "poultry": "IN_SCOPE_POULTRY",
    "general": "IN_SCOPE_GENERAL_AG",
}
EVAL_COUNTY_FIPS = "05031"  # Craighead County — SSURGO+NOAA injection succeeds


@dataclass
class ClassifiedItem:
    query: str
    bucket: Bucket
    human_bucket: Optional[str]
    abstained: bool
    rule_type: Optional[str]
    cond_preserved: Optional[bool] = None


def build_report(items: list[ClassifiedItem]) -> dict:
    counts = {b.value: 0 for b in Bucket}
    counts["B1"] = 0
    counts["B_ABSENT_answered"] = 0
    for it in items:
        if it.bucket is Bucket.B_ABSENT:
            if it.abstained:
                counts["B1"] += 1
            else:
                counts["B_ABSENT_answered"] += 1
        else:
            counts[it.bucket.value] += 1

    labeled = [it for it in items if it.human_bucket is not None]
    if labeled:
        agree = sum(1 for it in labeled if it.bucket.value == it.human_bucket)
        error_rate = round(1 - agree / len(labeled), 3)
    else:
        error_rate = None

    b2 = [it for it in items if it.bucket is Bucket.B2]
    if b2:
        cond = sum(1 for it in b2 if it.rule_type == "conditional")
        lever1_fraction = round(cond / len(b2), 3)
    else:
        lever1_fraction = None

    scored = [it for it in items
              if it.rule_type == "conditional" and it.cond_preserved is not None]
    if scored:
        kept = sum(1 for it in scored if it.cond_preserved)
        cond_rate = round(kept / len(scored), 3)
    else:
        cond_rate = None

    return {
        "counts": counts,
        "total": len(items),
        "judge_error_rate": error_rate,
        "calibration_n": len(labeled),
        "lever1_conditional_fraction_of_b2": lever1_fraction,
        "conditional_completeness_rate": cond_rate,
        "conditional_scored_n": len(scored),
    }


async def _classify_record(record: GoldRecord, run_rag_query) -> ClassifiedItem:
    category = _NAMESPACE_TO_CATEGORY.get(record.namespace, "IN_SCOPE_GENERAL_AG")
    result = await run_rag_query(
        message=record.query,
        county_fips=EVAL_COUNTY_FIPS,
        language="en",
        category=category,
        session_history=[],
    )
    advisory, chunks = result if isinstance(result, tuple) else (result, [])
    advisory_dict = advisory.model_dump() if hasattr(advisory, "model_dump") else advisory
    abstained = is_abstention(advisory_dict)

    if record.set_aside or not record.gold_found:
        judge = JudgeResult(span=None, partial=False)
        verified = False
    else:
        judge = judge_containment(record.gold_answer, chunks)
        verified = fact_retrieved(record.gold_snippet, judge.span, chunks)

    bucket = classify(record, judge, span_verified=verified)

    cond_preserved = None
    if (record.rule_type == "conditional" and record.gold_found
            and not record.set_aside):
        candidate = flatten_advisory(advisory_dict)
        cond_preserved = judge_conditional(record.gold_answer, candidate).preserved

    return ClassifiedItem(
        query=record.query, bucket=bucket, human_bucket=record.human_bucket,
        abstained=abstained, rule_type=record.rule_type,
        cond_preserved=cond_preserved,
    )


async def run_diagnostic(gold_path: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
    from services.rag import run_rag_query
    records = load_gold_records(gold_path)
    items = [await _classify_record(r, run_rag_query) for r in records]
    return build_report(items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True,
                        help="Path to the human gold-labeled sample JSONL")
    args = parser.parse_args()
    report = asyncio.run(run_diagnostic(args.gold))
    print("\n=== D3 BUCKET SPLIT ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
