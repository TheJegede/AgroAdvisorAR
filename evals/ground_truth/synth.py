"""OFFLINE answer-key synthesis runner (cost-gated — spends Gemini tokens).

Generates one grounded reference answer per eval query from its gold chunk(s).
Cost-gated: prints an estimate unless --confirm-cost is passed. The pure assembly
(build_records) is injected with the LLM call so it is unit-tested without spend.

NEVER imported by backend/rag.py or the request path.
"""
import argparse
import json
from pathlib import Path

from answer_keys import (load_gold_by_query, build_synthesis_prompt,
                         parse_answer_key, write_answer_keys, CLEAN_SET, ANSWER_KEYS)


def build_records(by_query: dict, call_llm) -> list[dict]:
    """Synthesize answer-key records. `call_llm(prompt)->str` is injected so this
    is pure/testable. Drops INSUFFICIENT/empty syntheses (parse_answer_key None)."""
    records = []
    for query, entry in by_query.items():
        raw = call_llm(build_synthesis_prompt(query, entry))
        rec = parse_answer_key(
            query, entry["namespace"],
            [c["chunk_id"] for c in entry["chunks"]],
            raw,
        )
        if rec is not None:
            records.append(rec)
    return records


def _gemini_call():
    """Build the real Gemini 2.5-flash synthesis call (distinct from generator)."""
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.environ["GOOGLE_API_KEY"], temperature=0,
    )
    return lambda prompt: llm.invoke(prompt).content


_COST_NOTE = """\
COST GATE — synthesis spends Gemini-2.5-flash tokens (~one grounded summary call
per eval query; ~198 calls for the clean set — cheap but non-zero).
Re-run with --confirm-cost to proceed."""


def main():
    ap = argparse.ArgumentParser(description="Synthesize answer keys (cost-gated).")
    ap.add_argument("--eval-set", type=Path, default=CLEAN_SET)
    ap.add_argument("--out", type=Path, default=ANSWER_KEYS)
    ap.add_argument("--confirm-cost", action="store_true")
    args = ap.parse_args()
    if not args.confirm_cost:
        print(_COST_NOTE)
        raise SystemExit(0)

    rows = [json.loads(l) for l in open(args.eval_set, encoding="utf-8") if l.strip()]
    by_q = load_gold_by_query(rows)
    records = build_records(by_q, call_llm=_gemini_call())
    write_answer_keys(records, args.out)
    n_drop = len(by_q) - len(records)
    print(f"answer keys: {len(records)} written, {n_drop} INSUFFICIENT/dropped -> {args.out}")


if __name__ == "__main__":
    main()
