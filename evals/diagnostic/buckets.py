# evals/diagnostic/buckets.py
"""Pure bucket decision tree (D2). No I/O — the judge result and the
deterministic span-verification outcome are passed in."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from evals.diagnostic.gold_schema import GoldRecord


class Bucket(str, Enum):
    B1 = "B1"            # correctly abstained (derived in the report layer)
    B2 = "B2"            # answerable, generation failed
    B3 = "B3"            # true corpus gap
    B4 = "B4"            # borderline / partial
    B_MISS = "B_MISS"    # retrieval miss (radioactive)
    B_ABSENT = "B_ABSENT"  # not in source of truth → feeds B1
    QUARANTINED = "QUARANTINED"  # set-aside hard case, no expert


@dataclass
class JudgeResult:
    span: Optional[str]
    partial: bool


def classify(record: GoldRecord, judge: JudgeResult, span_verified: bool) -> Bucket:
    if record.set_aside:
        return Bucket.QUARANTINED
    if not record.gold_found:
        return Bucket.B_ABSENT
    if judge.partial:
        return Bucket.B4
    if span_verified:
        return Bucket.B2
    # Span absent or failed deterministic verification → not in retrieved chunks.
    if record.source_in_index:
        return Bucket.B_MISS
    return Bucket.B3
