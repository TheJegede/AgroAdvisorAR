"""Per-stage latency probe for the RAG query pipeline.

Non-invasive: calls the same service functions the live `/query` path uses and
times each stage with perf_counter. Does NOT touch the prod path, auth, or SSE.
Warms models + connections first so numbers reflect a long-running server (prod),
not cold process startup.

Run from backend/ with the repo-root .env loaded:
    cd backend && python -m scripts.latency_probe
    cd backend && python -m scripts.latency_probe --lang es

Stages (each an LLM round-trip unless noted):
    translate_in  ES->EN bridge (ES runs only)
    classify      LLM #1  (8b classifier)
    embed         gte-base query embedding (CPU, on our host) -- NOT an LLM call
    retrieve      gte embed + Pinecone ANN fanout
    context       SSURGO + NOAA fetch (prod: concurrent w/ retrieve, 6h cached)
    generate      LLM #2  (70b structured advisory)
    guard         LLM #3 + #4 (decompose_claims THEN judge_claims_llm, serial)
"""
import argparse
import asyncio
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import config
from langchain_core.messages import SystemMessage, HumanMessage
from models.advisory import AdvisoryDraft, AdvisoryResponse
from services import citation_guard_v2, rag
from services.classifier import classify_query
from services.context import get_context
from services.embedding import MiniLMEmbeddings
from services.translation import translate_to_en
from utils.counties import get_county_info
from utils.prompt import build_system_prompt

QUERIES = [
    ("rice", "My rice leaves have brown lesions with gray centers, how do I treat it?"),
    ("soybeans", "What is the recommended seeding rate for soybeans in northeast Arkansas?"),
    ("poultry", "What broiler house temperature for 3 week old birds?"),
]


def _primary_llm():
    p = config.LLM_PRIMARY
    if p == "deepinfra":
        return "deepinfra", rag._get_deepinfra_llm()
    if p == "gemini":
        return "gemini", rag._get_llm()
    return "groq", rag._get_groq_llm()


async def _generate(messages):
    name, llm = _primary_llm()
    if llm is None:
        raise RuntimeError(f"primary provider {name} not configured (missing key)")
    if name == "deepinfra":
        from langchain_core.output_parsers import PydanticOutputParser
        fmt = PydanticOutputParser(pydantic_object=AdvisoryDraft).get_format_instructions()
        msgs = [SystemMessage(content=f"{m.content}\n\n{fmt}") if m.type == "system" else m
                for m in messages]
        return await llm.with_structured_output(AdvisoryDraft, method="json_mode").ainvoke(msgs)
    return await llm.with_structured_output(AdvisoryDraft).ainvoke(messages)


async def probe_one(message, lang, county_fips, emb, vs):
    marks = {}

    async def t_async(name, coro):
        s = time.perf_counter(); r = await coro; marks[name] = (time.perf_counter() - s) * 1000; return r

    def t_sync(name, fn, *a):
        s = time.perf_counter(); r = fn(*a); marks[name] = (time.perf_counter() - s) * 1000; return r

    if lang == "es":
        message = await t_async("translate_in", translate_to_en(message))

    category = await t_async("classify", classify_query(message))
    t_sync("embed", emb.embed_query, message)
    ns = rag._namespaces_for(category)
    fetch_k = config.RERANK_CANDIDATES if config.RERANK_ENABLED else config.TOP_K_RETRIEVAL
    docs = await t_async("retrieve", asyncio.to_thread(rag._fanout_search, vs, message, fetch_k, ns))
    ctx = await t_async("context", get_context(county_fips))
    soil, weather = ctx["soil"], ctx["weather"]

    ci = get_county_info(county_fips)
    sp = build_system_prompt(
        soil_context=soil, weather_context=weather, retrieved_docs=docs, session_history=[],
        language="en", is_safety_critical=False,
        county_name=(ci["county_name"] if ci else county_fips), awd_context=None, intent="diagnostic")
    msgs = [SystemMessage(content=sp), HumanMessage(content=message)]

    draft = await t_async("generate", _generate(msgs))
    adv = AdvisoryResponse(**draft.model_dump())
    prose = rag._advisory_to_verifiable_text(adv)
    chunks = [{"snippet": (d.page_content or "")[:500]} for d in docs]
    await t_async("guard", citation_guard_v2.verify_answer(prose, chunks))
    return marks, category, len(docs)


COLS = ["translate_in", "classify", "embed", "retrieve", "context", "generate", "guard"]
SERIAL_KEYS = ["translate_in", "classify", "retrieve", "generate", "guard"]  # what user waits for


def _row(label, marks):
    cells = "".join(f"{marks[k]:8.0f}" if marks.get(k) is not None else f"{'-':>8}" for k in COLS)
    serial = sum(marks.get(k, 0) for k in SERIAL_KEYS)
    return f"{label:<10}{cells}{serial:9.0f}"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "es"], default="en")
    args = ap.parse_args()
    fips = config.DEFAULT_COUNTY_FIPS

    print(f"LLM_PRIMARY={config.LLM_PRIMARY}  index={config.PINECONE_INDEX_NAME}  "
          f"embed={config.EMBEDDING_MODEL_PATH}  judge={getattr(config,'GROUNDEDNESS_JUDGE',None)}  "
          f"lang={args.lang}  county={fips}")

    # Warm models + connections (prod server is long-running; cold load is not per-query).
    emb = MiniLMEmbeddings(); emb.embed_query("warmup")
    vs = rag._get_vectorstore(); vs.similarity_search_with_score("warmup", k=1, namespace="rice")
    await classify_query("warmup")

    head = f"{'crop':<10}" + "".join(f"{h[:8]:>8}" for h in COLS) + f"{'SERIAL':>9}"
    print(head); print("-" * len(head))
    rows = []
    for crop, q in QUERIES:
        try:
            marks, cat, n = await probe_one(q, args.lang, fips, emb, vs)
            rows.append(marks)
            print(_row(crop, marks) + f"   [{cat} {n}d]")
        except Exception as e:
            print(f"{crop:<10} FAILED: {type(e).__name__}: {str(e)[:110]}")
    if rows:
        avg = {k: sum(m.get(k, 0) for m in rows) / len(rows) for k in COLS}
        print("-" * len(head)); print(_row("AVG", avg))
        print("\nms. SERIAL = critical-path sum (translate+classify+retrieve+generate+guard).")
        print("context runs concurrent w/ retrieve in prod (6h cached) -> excluded from SERIAL.")


if __name__ == "__main__":
    asyncio.run(main())
