"""Tag or filter eval rows whose gold chunks come from weak corpus sections.

This is for diagnosing whether a retrieval regression is real or mostly caused
by brittle single-gold targets such as abstracts, acknowledgments, references,
and table-only fragments.

Example:
    python evals/filter_eval_by_section.py \
      --eval-set evals/eval_set_v2_remap_v3.jsonl \
      --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl \
      --out evals/eval_set_v2_remap_v3_filtered.jsonl \
      --report evals/results/eval_set_v2_remap_v3_section_filter.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_WEAK_SECTIONS = {
    "abstract",
    "acknowledgment",
    "acknowledgments",
    "references",
}
TABLE_FRAGMENT_RE = re.compile(
    r"\b(table|fig\.|figure|lsd|p-value|treatment|replication|cultivar)\b",
    re.IGNORECASE,
)


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_corpus(path: Path) -> dict[str, dict]:
    return {row["chunk_id"]: row for row in read_jsonl(path)}


def classify_gold(row: dict, corpus_row: dict, weak_sections: set[str]) -> list[str]:
    reasons = []
    section = (corpus_row.get("section_heading") or "").strip().lower()
    source_text = corpus_row.get("source_text") or row.get("chunk_text") or ""
    if section in weak_sections:
        reasons.append(f"weak_section:{section}")
    if _looks_like_table_fragment(source_text):
        reasons.append("table_or_results_fragment")
    if not corpus_row:
        reasons.append("missing_corpus_gold")
    return reasons


def _looks_like_table_fragment(text: str) -> bool:
    if not text:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    short_numeric = sum(1 for line in lines if _line_is_numeric_tableish(line))
    return short_numeric >= 3 or (
        len(lines) <= 8 and bool(TABLE_FRAGMENT_RE.search(text)) and short_numeric >= 1
    )


def _line_is_numeric_tableish(line: str) -> bool:
    tokens = line.split()
    if len(tokens) < 3:
        return False
    numericish = sum(1 for token in tokens if re.search(r"\d", token))
    return numericish / len(tokens) >= 0.4


def tag_rows(rows: list[dict], corpus_by_id: dict[str, dict], weak_sections: set[str]) -> list[dict]:
    tagged = []
    for row in rows:
        corpus_row = corpus_by_id.get(row["chunk_id"], {})
        reasons = classify_gold(row, corpus_row, weak_sections)
        tagged.append({
            **row,
            "gold_document_title": corpus_row.get("document_title", ""),
            "gold_section_heading": corpus_row.get("section_heading", ""),
            "gold_filter_reasons": reasons,
        })
    return tagged


def summarize(tagged_rows: list[dict]) -> dict:
    reason_counts = Counter(
        reason
        for row in tagged_rows
        for reason in row["gold_filter_reasons"]
    )
    section_counts = Counter(row.get("gold_section_heading") or "" for row in tagged_rows)
    namespace_counts = Counter(row.get("namespace", "") for row in tagged_rows)
    filtered = [row for row in tagged_rows if row["gold_filter_reasons"]]
    return {
        "total": len(tagged_rows),
        "filtered": len(filtered),
        "kept": len(tagged_rows) - len(filtered),
        "filtered_by_namespace": dict(Counter(row.get("namespace", "") for row in filtered)),
        "reason_counts": dict(reason_counts.most_common()),
        "top_sections": dict(section_counts.most_common(20)),
        "namespace_counts": dict(namespace_counts.most_common()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, required=True)
    parser.add_argument("--corpus-jsonl", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tagged-out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--weak-sections",
        default=",".join(sorted(DEFAULT_WEAK_SECTIONS)),
        help="Comma-separated section headings to filter case-insensitively.",
    )
    args = parser.parse_args()

    weak_sections = {section.strip().lower() for section in args.weak_sections.split(",") if section.strip()}
    tagged = tag_rows(read_jsonl(args.eval_set), load_corpus(args.corpus_jsonl), weak_sections)
    kept = [row for row in tagged if not row["gold_filter_reasons"]]

    write_jsonl(kept, args.out)
    if args.tagged_out:
        write_jsonl(tagged, args.tagged_out)

    report = summarize(tagged)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Kept -> {args.out}")
    if args.tagged_out:
        print(f"Tagged -> {args.tagged_out}")
    if args.report:
        print(f"Report -> {args.report}")


if __name__ == "__main__":
    main()
