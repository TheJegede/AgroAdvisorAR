"""Apply Taiwo's round-2 verdicts (parsed from the round-2 doc) to answer_keys.jsonl.

CORRECT -> validate. DROP -> remove. EDIT -> apply (relabel general / change "X" to
"Y" / change-to full text) + validate. Every text EDIT is verified; a quoted "from"
string that does not match is NOT applied and is reported (left for manual fix).
$0, pure.
"""
import sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from answer_keys import load_answer_keys, write_answer_keys, ANSWER_KEYS

DOC = Path(__file__).parent.parent.parent / "docs/superpowers/2026-06-13-phase2-answer-key-validation-round2.md"

# Parse doc into {query -> verdict_text}
txt = DOC.read_text(encoding="utf-8")
verdicts = {}
for b in re.split(r"\n## \[", txt)[1:]:
    query = b.split("]", 1)[1].split("\n", 1)[0].strip()
    m = re.search(r"verdict:\*\*\s*(.*)", b)
    verdicts[query] = (m.group(1).strip().replace("**", "").strip() if m else "")

recs = load_answer_keys()
out, dropped, validated, misses, relabels, textedits = [], 0, 0, [], 0, 0
for query, rec in recs.items():
    v = verdicts.get(query)
    if v is None:               # not in round-2 doc (already round-1 validated) -> keep as-is
        out.append(rec); continue
    vl = v.lower()
    if vl.startswith("drop"):
        dropped += 1; continue
    # EDIT operations
    if "relabel namespace to general" in vl:
        rec["namespace"] = "general"; relabels += 1
    m_xy = re.search(r'Change "([^"]+)" to "([^"]+)"', v)
    m_to = re.search(r'Change to "([^"]+)"', v)
    if m_xy:
        old, new = m_xy.group(1), m_xy.group(2)
        if old in rec["reference_answer"]:
            rec["reference_answer"] = rec["reference_answer"].replace(old, new); textedits += 1
        else:
            misses.append((query[:60], old)); continue   # don't validate a failed edit
    elif m_to:
        rec["reference_answer"] = m_to.group(1); textedits += 1
    # CORRECT or successful EDIT -> validate
    rec["validated"] = True; validated += 1
    out.append(rec)

write_answer_keys(out, ANSWER_KEYS)
print(f"kept {len(out)} | dropped {dropped} | validated {validated} "
      f"(relabels {relabels}, text-edits {textedits})")
print(f"total validated in file: {sum(1 for r in out if r['validated'])}")
if misses:
    print("\n!! EDIT MISSES (quoted 'from' not found - left unvalidated, fix manually):")
    for q, old in misses:
        print(f"   [{q}] could not find: {old!r}")
