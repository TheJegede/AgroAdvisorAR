"""Audit failed retrieval-v3 eval rows.

The matrix summary says whether a candidate wins. This script explains why it
lost by comparing original gold chunks, v3 remapped gold chunks, and dense top-k
results for failed rows.

Example:
    python evals/audit_retrieval_v3_failures.py \
      --original-eval evals/eval_set_v2.jsonl \
      --remapped-eval evals/eval_set_v2_remap_v3.jsonl \
      --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl \
      --index agroar-prod-retrieval-v3-gte \
      --namespace rice \
      --limit 20
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from textwrap import shorten
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

RESULTS_DIR = Path(__file__).parent / "results"
TOKEN_RE = re.compile(r"[a-z0-9]+")


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall((text or "").lower()))


def token_overlap(a: str, b: str) -> float:
    toks = token_set(a)
    if not toks:
        return 0.0
    return len(toks & token_set(b)) / len(toks)


def load_corpus(path: Path) -> dict[str, dict]:
    return {row["chunk_id"]: row for row in read_jsonl(path)}


def dense_query(
    query: str,
    *,
    namespace: str,
    model,
    index,
    top_k: int,
) -> list[dict]:
    vector = model.encode(query, normalize_embeddings=True).tolist()
    result = index.query(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        include_values=False,
        include_metadata=True,
    )
    return list(result.get("matches", []))


def audit_failures(
    original_items: list[dict],
    remapped_items: list[dict],
    corpus_by_id: dict[str, dict],
    *,
    model_name: str,
    index_name: str,
    namespace: str,
    top_k: int,
    limit: int,
) -> dict:
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(index_name)

    rows = []
    all_namespace = [
        (i, original, remapped)
        for i, (original, remapped) in enumerate(zip(original_items, remapped_items), start=1)
        if remapped.get("namespace") == namespace
    ]

    for item_number, original, remapped in all_namespace:
        matches = dense_query(
            remapped["query"],
            namespace=namespace,
            model=model,
            index=index,
            top_k=top_k,
        )
        ranked_ids = [match["id"] for match in matches]
        if remapped["chunk_id"] in ranked_ids[:top_k]:
            continue

        gold = corpus_by_id.get(remapped["chunk_id"], {})
        top = [_format_match(match, corpus_by_id) for match in matches[:5]]
        rows.append({
            "item_number": item_number,
            "query": remapped["query"],
            "namespace": namespace,
            "gold_chunk_id": remapped["chunk_id"],
            "gold_rank_top_k": None,
            "original_gold_chunk_id": original.get("chunk_id", ""),
            "original_gold_text": original.get("chunk_text", ""),
            "v3_gold_source_text": gold.get("source_text", ""),
            "v3_gold_retrieval_header": gold.get("retrieval_header", ""),
            "v3_gold_document_title": gold.get("document_title", ""),
            "v3_gold_section_heading": gold.get("section_heading", ""),
            "gold_text_overlap": round(
                token_overlap(original.get("chunk_text", ""), gold.get("source_text", "")),
                4,
            ),
            "gold_header_chars": len(gold.get("retrieval_header", "")),
            "top_matches": top,
        })
        if len(rows) >= limit:
            break

    overlap_values = [row["gold_text_overlap"] for row in rows]
    header_lengths = [row["gold_header_chars"] for row in rows]
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model_name,
        "index": index_name,
        "namespace": namespace,
        "top_k": top_k,
        "audited_failures": len(rows),
        "namespace_items": len(all_namespace),
        "summary": {
            "mean_gold_text_overlap": round(mean(overlap_values), 4) if overlap_values else 0.0,
            "low_overlap_count_lt_0_5": sum(1 for value in overlap_values if value < 0.5),
            "mean_gold_header_chars": round(mean(header_lengths), 1) if header_lengths else 0.0,
            "same_title_top1_count": sum(
                1
                for row in rows
                if row["top_matches"]
                and row["top_matches"][0]["document_title"] == row["v3_gold_document_title"]
            ),
            "same_section_top1_count": sum(
                1
                for row in rows
                if row["top_matches"]
                and row["top_matches"][0]["section_heading"] == row["v3_gold_section_heading"]
            ),
        },
        "failures": rows,
    }


def _format_match(match: dict, corpus_by_id: dict[str, dict]) -> dict:
    chunk_id = match["id"]
    record = corpus_by_id.get(chunk_id, {})
    metadata = match.get("metadata") or {}
    return {
        "chunk_id": chunk_id,
        "score": round(float(match.get("score", 0.0)), 4),
        "document_title": record.get("document_title") or metadata.get("document_title", ""),
        "section_heading": record.get("section_heading") or metadata.get("section_heading", ""),
        "retrieval_header": record.get("retrieval_header") or metadata.get("retrieval_header", ""),
        "source_preview": shorten(
            re.sub(r"\s+", " ", record.get("source_text") or metadata.get("text", "")),
            width=260,
            placeholder="...",
        ),
    }


def write_markdown(payload: dict, out_path: Path) -> None:
    lines = [
        "# Retrieval v3 Failure Audit",
        "",
        f"- Index: `{payload['index']}`",
        f"- Namespace: `{payload['namespace']}`",
        f"- Audited failures: `{payload['audited_failures']}` / `{payload['namespace_items']}` namespace items",
        f"- Mean original-to-v3 gold overlap: `{payload['summary']['mean_gold_text_overlap']}`",
        f"- Low-overlap failures `<0.5`: `{payload['summary']['low_overlap_count_lt_0_5']}`",
        f"- Mean gold header chars: `{payload['summary']['mean_gold_header_chars']}`",
        f"- Same-title top1 failures: `{payload['summary']['same_title_top1_count']}`",
        f"- Same-section top1 failures: `{payload['summary']['same_section_top1_count']}`",
        "",
    ]
    for row in payload["failures"]:
        lines.extend([
            f"## Item {row['item_number']}",
            "",
            f"Query: {row['query']}",
            "",
            f"Gold: `{row['gold_chunk_id']}` | overlap `{row['gold_text_overlap']}`",
            "",
            f"Gold title/section: {row['v3_gold_document_title']} | {row['v3_gold_section_heading']}",
            "",
            f"Gold header: {row['v3_gold_retrieval_header']}",
            "",
            "Top matches:",
        ])
        for i, match in enumerate(row["top_matches"], start=1):
            lines.extend([
                f"{i}. `{match['chunk_id']}` score `{match['score']}`",
                f"   {match['document_title']} | {match['section_heading']}",
                f"   {match['source_preview']}",
            ])
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-eval", type=Path, default=Path(__file__).parent / "eval_set_v2.jsonl")
    parser.add_argument("--remapped-eval", type=Path, default=Path(__file__).parent / "eval_set_v2_remap_v3.jsonl")
    parser.add_argument("--corpus-jsonl", type=Path, required=True)
    parser.add_argument("--model", default="thenlper/gte-base")
    parser.add_argument("--index", default="agroar-prod-retrieval-v3-gte")
    parser.add_argument("--namespace", default="rice")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    payload = audit_failures(
        read_jsonl(args.original_eval),
        read_jsonl(args.remapped_eval),
        load_corpus(args.corpus_jsonl),
        model_name=args.model,
        index_name=args.index,
        namespace=args.namespace,
        top_k=args.top_k,
        limit=args.limit,
    )

    RESULTS_DIR.mkdir(exist_ok=True)
    out = args.out or RESULTS_DIR / f"retrieval_v3_failure_audit_{args.namespace}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_out = out.with_suffix(".md")
    write_markdown(payload, md_out)
    print(json.dumps(payload["summary"], indent=2))
    print(f"Saved -> {out}")
    print(f"Saved -> {md_out}")


if __name__ == "__main__":
    main()
