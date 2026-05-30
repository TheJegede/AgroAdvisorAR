"""Remap eval_set_v2 gold chunk_ids onto a re-chunked corpus WITHOUT an LLM.

After token re-chunking, the old 512-char gold chunk_ids no longer exist. Each
eval item still carries the gold `chunk_text`; this finds the new chunk (same
namespace) with the highest token overlap with that gold span and rewrites the
item's chunk_id. Lets retrieval eval run on the identical 200 queries against
the new index for a true apples-to-apples delta — no Groq/LLM calls.

Run: python evals/remap_eval_set.py --out evals/eval_set_v2_remap.jsonl
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))

from extractor import extract_text, extract_tables_as_text  # noqa: E402
from chunker import chunk_document  # noqa: E402

RAW_PDFS_DIR = Path(__file__).parent.parent / "ingestion" / "raw_pdfs"
DEFAULT_EVAL = Path(__file__).parent / "eval_set_v2.jsonl"
CROP_PREFIXES = {"rice", "soybeans", "poultry", "general"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _toks(text: str) -> set:
    return set(_TOKEN_RE.findall(text.lower()))


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def best_new_chunk_id(gold_text: str, namespace: str, new_docs: list) -> str | None:
    """chunk_id of the same-namespace new chunk with max token overlap vs gold."""
    gold = _toks(gold_text)
    if not gold:
        return None
    best_id, best_score = None, 0.0
    for d in new_docs:
        if d.metadata.get("crop_type") != namespace:
            continue
        overlap = len(gold & _toks(d.page_content)) / len(gold)
        if overlap > best_score:
            best_id, best_score = d.metadata["chunk_id"], overlap
    return best_id


def chunk_all_pdfs() -> list:
    docs = []
    for pdf_path in sorted(RAW_PDFS_DIR.glob("*.pdf")):
        crop = _infer_crop_type(pdf_path.name)
        text = extract_text(str(pdf_path))
        tables = extract_tables_as_text(str(pdf_path))
        if tables:
            text += "\n\n" + "\n\n".join(tables)
        title = pdf_path.stem.replace("_", " ").replace("-", " ")
        docs.extend(chunk_document(
            text, document_title=title,
            source_url=f"file://{pdf_path.resolve()}", crop_type=crop,
        ))
    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "eval_set_v2_remap.jsonl")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.eval_set, encoding="utf-8")]
    new_docs = chunk_all_pdfs()
    print(f"Re-chunked {len(new_docs)} new chunks; remapping {len(items)} eval items...")

    out, dropped = [], 0
    for it in items:
        nid = best_new_chunk_id(it["chunk_text"], it["namespace"], new_docs)
        if nid is None:
            dropped += 1
            continue
        out.append({**it, "chunk_id": nid})

    with open(args.out, "w", encoding="utf-8") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"Wrote {len(out)} remapped items ({dropped} dropped) -> {args.out}")


if __name__ == "__main__":
    main()
