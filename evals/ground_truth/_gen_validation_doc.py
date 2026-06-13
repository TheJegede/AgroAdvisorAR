"""One-shot: render the Task 5b human-validation sample to markdown. $0, pure."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from answer_keys import load_answer_keys, validation_sample

recs = list(load_answer_keys().values())
sample = validation_sample(recs)  # 5/namespace, seed=7
out = Path(__file__).parent.parent.parent / "docs/superpowers/2026-06-13-phase2-answer-key-validation.md"
lines = [
    "# Phase 2 Answer-Key Validation",
    "",
    f"Synthesized {len(recs)} answer keys (100 kept / 97 INSUFFICIENT-dropped: "
    "gold chunk did not contain the answer). Review each below.",
    "Mark each `verdict:` as **CORRECT** / **EDIT: <fix>** / **DROP**.",
    "Sign-off gates any NIW/arXiv use of the multi-reference correctness number.",
    "",
    f"Sample: {len(sample)} items (stratified ~5/namespace, seed=7).",
    "",
]
for r in sample:
    lines.append(f"## [{r['namespace']}] {r['query']}")
    lines.append(f"- **ref:** {r['reference_answer']}")
    lines.append(f"- **source_chunk_ids:** {r['source_chunk_ids']}")
    lines.append("- **verdict:** ")
    lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"validation doc written: {len(sample)} items -> {out}")
