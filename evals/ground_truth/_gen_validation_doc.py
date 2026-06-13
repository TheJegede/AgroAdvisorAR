"""Render Task 5b human-validation docs to markdown. $0, pure.

--round2: dump ALL not-yet-validated keys (grouped by namespace) for review.
default : the seed=7 stratified 15-item sample (round 1).
"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from answer_keys import load_answer_keys, validation_sample

ap = argparse.ArgumentParser()
ap.add_argument("--round2", action="store_true")
args = ap.parse_args()

recs = list(load_answer_keys().values())
docs = Path(__file__).parent.parent.parent / "docs/superpowers"

if args.round2:
    pending = [r for r in recs if not r.get("validated")]
    pending.sort(key=lambda r: (str(r["namespace"]), r["query"]))
    out = docs / "2026-06-13-phase2-answer-key-validation-round2.md"
    lines = [
        "# Phase 2 Answer-Key Validation — Round 2 (remaining keys)",
        "",
        f"{len(pending)} not-yet-validated keys, grouped by namespace.",
        "Mark each `verdict:` as **CORRECT** / **EDIT: <fix>** / **DROP**.",
        "Blank = stays validated:false (won't score). Sign-off gates NIW/arXiv use.",
        "",
    ]
    cur = None
    for r in pending:
        if r["namespace"] != cur:
            cur = r["namespace"]
            lines.append(f"\n# === {cur} ===\n")
        lines.append(f"## [{r['namespace']}] {r['query']}")
        lines.append(f"- **ref:** {r['reference_answer']}")
        lines.append(f"- **source_chunk_ids:** {r['source_chunk_ids']}")
        lines.append("- **verdict:** ")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"round-2 doc written: {len(pending)} keys -> {out}")
else:
    sample = validation_sample(recs)
    out = docs / "2026-06-13-phase2-answer-key-validation.md"
    lines = [
        "# Phase 2 Answer-Key Validation", "",
        f"Synthesized {len(recs)} answer keys. Review each below.",
        "Mark each `verdict:` as **CORRECT** / **EDIT: <fix>** / **DROP**.", "",
        f"Sample: {len(sample)} items (stratified ~5/namespace, seed=7).", "",
    ]
    for r in sample:
        lines.append(f"## [{r['namespace']}] {r['query']}")
        lines.append(f"- **ref:** {r['reference_answer']}")
        lines.append(f"- **source_chunk_ids:** {r['source_chunk_ids']}")
        lines.append("- **verdict:** ")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"validation doc written: {len(sample)} items -> {out}")
