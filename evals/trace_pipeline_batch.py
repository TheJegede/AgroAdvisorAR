"""Diagnostic: run several real queries through the REAL end-to-end pipeline
and summarize the citation-guard outcome (confidence, NLI score, whether the
body was suppressed/escalated). Shows whether the guard fixes generalize past
the single A/B query.

Run:  python evals/trace_pipeline_batch.py
"""
import os
import sys
import json
import asyncio

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
os.chdir(os.path.join(_ROOT, "backend"))

from services.rag import run_rag_query  # noqa: E402
import config  # noqa: E402

_NS_TO_CAT = {
    "rice": "IN_SCOPE_RICE",
    "soybeans": "IN_SCOPE_SOYBEANS",
    "poultry": "IN_SCOPE_POULTRY",
}
COUNTY_FIPS = "05001"


def _load_samples(n_per_ns=2):
    rows = [json.loads(l) for l in open(os.path.join(_ROOT, "evals", "eval_set_v2.jsonl"), encoding="utf-8")]
    by_ns = {}
    for r in rows:
        by_ns.setdefault(r["namespace"], []).append(r)
    out = []
    for ns, items in by_ns.items():
        out.extend(items[:n_per_ns])
    return out


async def _run():
    print(f"LLM_PRIMARY={config.LLM_PRIMARY}  INDEX={config.PINECONE_INDEX_NAME}\n")
    samples = _load_samples()
    rows = []
    for r in samples:
        cat = _NS_TO_CAT[r["namespace"]]
        try:
            adv, _ = await run_rag_query(
                message=r["query"], county_fips=COUNTY_FIPS, language="en",
                category=cat, session_history=[],
            )
            suppressed = adv.problem_summary == "" and not adv.recommended_actions
            rows.append({
                "ns": r["namespace"],
                "conf": adv.confidence,
                "score": adv.confidence_score,
                "suppressed": suppressed,
                "escalated": adv.escalation is not None,
                "n_actions": len(adv.recommended_actions),
                "q": r["query"][:60],
            })
        except Exception as e:
            rows.append({"ns": r["namespace"], "error": str(e)[:120], "q": r["query"][:60]})

    print(f"{'ns':<9}{'conf':<7}{'score':<7}{'suppr':<7}{'escal':<7}{'acts':<5} query")
    for x in rows:
        if "error" in x:
            print(f"{x['ns']:<9}ERROR: {x['error']}  | {x['q']}")
            continue
        score = f"{x['score']:.2f}" if x["score"] is not None else "None"
        print(f"{x['ns']:<9}{x['conf']:<7}{score:<7}{str(x['suppressed']):<7}"
              f"{str(x['escalated']):<7}{x['n_actions']:<5} {x['q']}")

    ok = [x for x in rows if "error" not in x]
    if ok:
        n_suppr = sum(1 for x in ok if x["suppressed"])
        n_escal = sum(1 for x in ok if x["escalated"])
        print(f"\nN={len(ok)}  suppressed={n_suppr}  escalated={n_escal}")


if __name__ == "__main__":
    asyncio.run(_run())
