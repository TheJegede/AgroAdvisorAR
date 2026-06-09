# evals/diagnostic/gold_schema.py
"""Schema + loader for the human-produced gold-label sample (D2 input)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

VALID_RULE_TYPES = {"conditional", "flat"}
VALID_BUCKETS = {"B1", "B2", "B3", "B4", "B_MISS", "B_ABSENT"}


class GoldSchemaError(ValueError):
    """Raised when a gold-label record violates the schema."""


@dataclass
class GoldRecord:
    query: str
    namespace: str
    gold_found: bool
    gold_answer: Optional[str]
    gold_source: Optional[str]
    gold_snippet: Optional[str]
    source_in_index: Optional[bool]
    rule_type: Optional[str]
    human_bucket: Optional[str]
    set_aside: bool
    set_aside_reason: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "GoldRecord":
        if not d.get("query"):
            raise GoldSchemaError("query is required")
        gold_found = bool(d.get("gold_found"))
        if gold_found and not d.get("gold_snippet"):
            raise GoldSchemaError(
                "gold_found=True requires a gold_snippet (transcribe-don't-invent rule)"
            )
        rule_type = d.get("rule_type")
        if rule_type is not None and rule_type not in VALID_RULE_TYPES:
            raise GoldSchemaError(f"rule_type must be one of {VALID_RULE_TYPES}, got {rule_type!r}")
        human_bucket = d.get("human_bucket")
        if human_bucket is not None and human_bucket not in VALID_BUCKETS:
            raise GoldSchemaError(f"human_bucket must be one of {VALID_BUCKETS}, got {human_bucket!r}")
        return cls(
            query=d["query"],
            namespace=d.get("namespace", "general"),
            gold_found=gold_found,
            gold_answer=d.get("gold_answer"),
            gold_source=d.get("gold_source"),
            gold_snippet=d.get("gold_snippet"),
            source_in_index=d.get("source_in_index"),
            rule_type=rule_type,
            human_bucket=human_bucket,
            set_aside=bool(d.get("set_aside")),
            set_aside_reason=d.get("set_aside_reason"),
        )


def load_gold_records(path: Path) -> list[GoldRecord]:
    records = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(GoldRecord.from_dict(json.loads(line)))
    return records
