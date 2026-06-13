"""One-shot: apply Taiwo's Task 5b human verdicts to answer_keys.jsonl. $0, pure.

Verdicts keyed by the deterministic validation_sample (seed=7) index 1..15.
DROP removes the record; EDIT-keep applies the fix + validates; CORRECT validates.
Unreviewed keys (outside the sample) stay validated:false -> never score.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from answer_keys import load_answer_keys, validation_sample, write_answer_keys, ANSWER_KEYS

recs = load_answer_keys()                       # {query -> record}, file order
sample = validation_sample(list(recs.values())) # 15 records, deterministic
q = [r["query"] for r in sample]                # index 0..14 == sample item 1..15

# Verdicts (1-indexed in the doc -> 0-indexed here)
DROP = {q[2], q[7], q[8], q[9]}                 # items 3, 8, 9, 10
NS_GENERAL = {q[0], q[4]}                        # items 1, 5
REF_EDIT = {q[6]: ("Provisia/Maximazamox Ace rice", "Provisia/Max-Ace rice")}  # item 7
VALIDATE = {q[i] for i in range(15)} - DROP     # all reviewed non-drops -> 11

out = []
for query, rec in recs.items():
    if query in DROP:
        continue
    if query in NS_GENERAL:
        rec["namespace"] = "general"
    if query in REF_EDIT:
        old, new = REF_EDIT[query]
        rec["reference_answer"] = rec["reference_answer"].replace(old, new)
    if query in VALIDATE:
        rec["validated"] = True
    out.append(rec)

write_answer_keys(out, ANSWER_KEYS)
n_val = sum(1 for r in out if r["validated"])
print(f"applied: {len(out)} records kept ({len(recs)-len(out)} dropped), "
      f"{n_val} validated, {len(out)-n_val} unreviewed(validated:false)")
# sanity: REF_EDIT landed
for r in out:
    if r["query"] in REF_EDIT:
        assert "Max-Ace" in r["reference_answer"] and "Maximazamox" not in r["reference_answer"]
        print("  ref-edit #7 applied OK")
