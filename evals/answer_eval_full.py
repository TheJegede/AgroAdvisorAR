"""End-to-end answer eval: correctness + faithfulness on held-out queries.

For each sampled query, runs the production RAG chain (real retrieval + Gemini,
Groq fallback) and scores the advisory two ways with a Groq llama-70b judge:
  correctness  — does the advisory correctly answer the query using the gold
                 reference passage? (reuses evals/judge.score_item)
  faithfulness — is every claim in the advisory supported by the chunks the
                 model ACTUALLY retrieved? (hallucination check, gold-independent)

Run:  python evals/answer_eval_full.py --sample 15
Needs GROQ_API_KEY (judge + generation fallback) and GOOGLE_API_KEY in .env.
"""
import sys, os, json, asyncio, argparse, re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import services.rag as rag                        # noqa: E402
import config                                      # noqa: E402
from services.rag import run_rag_query             # noqa: E402
from judge import score_item, sample_items, _summarize_advisory  # noqa: E402
from langchain_groq import ChatGroq               # noqa: E402
from langchain_core.messages import SystemMessage, HumanMessage  # noqa: E402


def _force_groq_generation():
    """Route the production chain's generation through Groq (dodges Gemini's
    20/day free quota). citation_guard claim-decomp still tries Gemini but has a
    sentence fallback; the NLI cross-encoder is local."""
    rag._llm = ChatGroq(model=os.environ.get("GEN_MODEL", "llama-3.3-70b-versatile"),
                        api_key=os.environ["GROQ_API_KEY"], temperature=0.1)


def _is_suppressed(adv: dict) -> bool:
    """The NLI guard blanks low-confidence advisories (problem_summary='' +
    escalation warning)."""
    return not (adv.get("problem_summary") or "").strip() and not adv.get("recommended_actions")

EVAL_SET = Path(__file__).parent / "eval_set_v2.jsonl"
EVAL_COUNTY_FIPS = "05031"  # Craighead County, AR
_NS_TO_CAT = {"rice": "IN_SCOPE_RICE", "soybeans": "IN_SCOPE_SOYBEANS",
              "poultry": "IN_SCOPE_POULTRY", "general": "IN_SCOPE_GENERAL_AG"}

FAITH_SYS = (
    "You are auditing a RAG agricultural advisory for faithfulness. You see the "
    "advisory and the ONLY source passages the system retrieved. Judge whether the "
    "advisory's factual claims (causes, actions, products, rates) are supported by "
    "those passages. Unsupported specifics (invented rates, products, numbers) are "
    "hallucinations — penalize them. General safe framing is fine."
)
FAITH_USER = """ADVISORY:
{answer}

RETRIEVED SOURCE PASSAGES (the only context the model had):
{context}

Return ONLY JSON: {{"score": <1.0 | 0.5 | 0.0>, "rationale": "<one short sentence>"}}
- 1.0 — all substantive claims supported by the passages
- 0.5 — mostly supported, minor unsupported detail
- 0.0 — key claims unsupported / hallucinated / contradict the passages"""

_judge = None


def _get_judge():
    global _judge
    if _judge is None:
        _judge = ChatGroq(model=os.environ.get("JUDGE_MODEL", "llama-3.3-70b-versatile"),
                          api_key=os.environ["GROQ_API_KEY"], temperature=0)
    return _judge


def _parse_score(raw):
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            p = json.loads(m.group(0))
            return max(0.0, min(1.0, float(p.get("score", 0.0)))), p.get("rationale", "")
        except Exception:
            pass
    return 0.0, f"parse fail: {raw[:120]}"


def faithfulness(advisory: dict, chunks: list[dict]) -> tuple[float, str]:
    ctx = "\n\n".join(
        f"[{c.get('document_title','')}] {c.get('snippet','')}" for c in chunks
    ) or "(no chunks retrieved)"
    resp = _get_judge().invoke([
        SystemMessage(content=FAITH_SYS),
        HumanMessage(content=FAITH_USER.format(answer=_summarize_advisory(advisory), context=ctx[:6000])),
    ])
    return _parse_score(resp.content)


async def evaluate(item):
    cat = _NS_TO_CAT.get(item["namespace"], "IN_SCOPE_GENERAL_AG")
    advisory, chunks = await run_rag_query(
        message=item["query"], county_fips=EVAL_COUNTY_FIPS, language="en",
        category=cat, session_history=[],
    )
    adv = advisory.model_dump() if hasattr(advisory, "model_dump") else advisory
    suppressed = _is_suppressed(adv)
    corr, c_r = score_item(item["query"], adv, item["chunk_text"])
    faith, f_r = faithfulness(adv, chunks)
    return corr, faith, suppressed, c_r, f_r


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=15)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--provider", choices=["gemini", "groq"], default="gemini",
                    help="groq routes generation through Groq (avoids Gemini quota)")
    ap.add_argument("--no-guard", action="store_true",
                    help="disable NLI suppression to measure raw answer quality")
    args = ap.parse_args()

    if args.provider == "groq":
        _force_groq_generation()
    if args.no_guard:
        config.NLI_CITATION_GUARD_ENABLED = False
    print(f"provider={args.provider}  guard={'off' if args.no_guard else 'on'}")

    items = [json.loads(l) for l in open(EVAL_SET, encoding="utf-8")]
    sample = sample_items(items, args.sample, seed=args.seed)

    corr_s, faith_s, n_supp, skipped = [], [], 0, 0
    for i, it in enumerate(sample, 1):
        try:
            corr, faith, suppressed, c_r, f_r = await evaluate(it)
            corr_s.append(corr)
            faith_s.append(faith)
            n_supp += 1 if suppressed else 0
            tag = "SUPPRESSED" if suppressed else f"corr={corr:.1f} faith={faith:.1f}"
            print(f"[{i}/{len(sample)}] {it['namespace']:>8} {tag} | {c_r[:45]} || {f_r[:45]}")
        except Exception as e:
            skipped += 1
            print(f"[{i}/{len(sample)}] SKIPPED {type(e).__name__}: {str(e)[:80]}")

    n = len(corr_s)
    print("\n=== END-TO-END ANSWER EVAL ===")
    print(f"scored={n} skipped={skipped}")
    if n:
        print(f"suppression rate: {100*n_supp/n:.0f}%  ({n_supp}/{n})")
        print(f"correctness  mean: {100*sum(corr_s)/n:.1f}%")
        print(f"faithfulness mean: {100*sum(faith_s)/n:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
