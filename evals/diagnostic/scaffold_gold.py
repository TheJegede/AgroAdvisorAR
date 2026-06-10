# evals/diagnostic/scaffold_gold.py
"""Machine-scaffold the gold-label candidate file (Track A2).

Fills only the *mechanical* fields (query, namespace, source_in_index) so the
human pass (see docs/gold-labeling-guide.md) just transcribes gold answers +
assigns buckets. The human fields are left null — transcribe-don't-invent.

Pure record-shaping (`build_candidate_record` / `scaffold`) is unit-tested with
an injected title-lookup; only `main()` hits Pinecone via the real index.
"""
import json
import argparse
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

DEFAULT_EVAL_SET = Path(__file__).parent.parent / "eval_set_v2.jsonl"
DEFAULT_OUT = Path(__file__).parent / "gold_labels.candidate.jsonl"


def build_candidate_record(query: str, namespace: str, source_in_index: Optional[bool]) -> dict:
    """One unfinished gold record: mechanical fields set, human fields null."""
    return {
        "query": query,
        "namespace": namespace,
        "source_in_index": source_in_index,
        "gold_found": None,
        "gold_answer": None,
        "gold_source": None,
        "gold_snippet": None,
        "rule_type": None,
        "human_bucket": None,
        "set_aside": False,
        "set_aside_reason": None,
    }


def scaffold(items: Iterable[dict], title_in_index: Callable[[str], bool]) -> list[dict]:
    """Shape each eval item into a candidate record.

    `title_in_index(document_title) -> bool` is injected so tests never hit
    Pinecone. A missing document_title yields source_in_index=None (unknown).
    """
    records = []
    for it in items:
        title = it.get("document_title")
        source_in_index = title_in_index(title) if title else None
        records.append(
            build_candidate_record(it["query"], it.get("namespace", "general"), source_in_index)
        )
    return records


def iter_eval_items(path: Path) -> Iterator[dict]:
    """Yield {query, namespace, document_title} from an eval-set JSONL."""
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            yield {
                "query": d["query"],
                "namespace": d.get("namespace", "general"),
                "document_title": d.get("document_title"),
            }


def write_candidates(records: Iterable[dict], out_path: Path) -> None:
    with Path(out_path).open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _real_title_lookup() -> Callable[[str], bool]:
    """Bind the live Pinecone index + embedder once; return a title->bool fn."""
    from evals.diagnostic.source_index import doc_title_in_index, _default_index_and_embed
    index, embed = _default_index_and_embed()
    return lambda title: doc_title_in_index(title, index=index, embed=embed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET,
                        help="JSONL of queries to scaffold (default eval_set_v2.jsonl)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="Output candidate JSONL")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only scaffold the first N items")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip the live Pinecone lookup; leave source_in_index null")
    args = parser.parse_args()

    items = list(iter_eval_items(args.eval_set))
    # Dedupe by (query, document_title) while preserving order.
    seen = set()
    deduped = []
    for it in items:
        key = (it["query"], it["document_title"])
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    if args.limit is not None:
        deduped = deduped[: args.limit]

    title_lookup = (lambda _t: None) if args.no_index else _real_title_lookup()
    records = scaffold(deduped, title_lookup)
    write_candidates(records, args.out)
    print(f"Wrote {len(records)} candidate records -> {args.out}")
    print("Next: fill the human fields per docs/gold-labeling-guide.md, "
          "then save as evals/diagnostic/gold_labels.jsonl")


if __name__ == "__main__":
    main()
