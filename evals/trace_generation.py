"""Diagnostic: run ONE query through the REAL end-to-end pipeline and dump the
advisory the frontend would render — generation output, confidence, and the
citation-guard outcome. Retrieval was already verified good by trace_retrieval.py,
so this isolates generation + guard.

Run:  python evals/trace_generation.py
"""
import os
import sys
import asyncio

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))
_BACKEND = os.path.join(_ROOT, "backend")
sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

from services.rag import run_rag_query  # noqa: E402
import config  # noqa: E402

QUERY = ("How do I make sure I'm putting out the right amount of spray on my "
         "fields, I don't wanna waste chemical or miss spots?")
CATEGORY = "IN_SCOPE_SOYBEANS"
COUNTY_FIPS = "05001"  # Arkansas County, AR


async def _run():
    print(f"LLM_PRIMARY={config.LLM_PRIMARY}  INDEX={config.PINECONE_INDEX_NAME}  "
          f"EMB={config.EMBEDDING_MODEL_PATH}\n")
    advisory, chunks = await run_rag_query(
        message=QUERY,
        county_fips=COUNTY_FIPS,
        language="en",
        category=CATEGORY,
        session_history=[],
    )
    print(f"Q: {QUERY}\n")
    print("=== ADVISORY (what the frontend renders) ===")
    print(advisory.model_dump_json(indent=2))
    print(f"\nretrieved_chunks={len(chunks)}")


if __name__ == "__main__":
    asyncio.run(_run())
