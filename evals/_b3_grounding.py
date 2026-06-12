"""Task 4 Step 1 — verbatim/number-grounding rate of stated rates in the B2 dump.

Reads products_rates + chunk_snippets (added to the dump by the --two-step task)
and reports how often each stated rate's numbers appear in the retrieved chunks.
A high rate => B1 already grounds rates => B3 (source_quote) is redundant."""
import json
import re

PATH = "evals/_out_clean_indepjudge_twostep.jsonl"

rows = [json.loads(l) for l in open(PATH, encoding="utf-8")]
total = grounded = 0
for r in rows:
    chunks = " ".join(r.get("chunk_snippets") or []).lower()
    for p in (r.get("products_rates") or []):
        rate = (p.get("rate") or "").strip().lower()
        if not rate:
            continue
        total += 1
        nums = re.findall(r"\d+\.?\d*", rate)
        if rate in chunks or (nums and all(n in chunks for n in nums)):
            grounded += 1

pct = 100 * grounded / max(total, 1)
print(f"rates stated: {total}  verbatim/number-grounded in retrieved chunks: "
      f"{grounded} ({pct:.0f}%)")
