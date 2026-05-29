"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
import logging
from datetime import date as _date
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryResponse
from services.embedding import MiniLMEmbeddings, BGEEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
from services import citation_guard_v2
from utils.prompt import build_system_prompt
from utils.counties import get_county_info
import config

logger = logging.getLogger(__name__)

_vectorstore: PineconeVectorStore | None = None
_vectorstore_es: PineconeVectorStore | None = None
_VECTORSTORE_ES_UNAVAILABLE = object()  # sentinel: init failed, don't retry
_llm: ChatGoogleGenerativeAI | None = None
_groq_llm = None
_groq_fast_llm = None


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(
            model=config.GROQ_PRIMARY_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_llm


def _get_groq_fast_llm():
    """8b-instant — far higher free tokens-per-day than 70b. Generation fallback
    when 70b hits its TPD cap, so the free tier survives pilot load."""
    global _groq_fast_llm
    if _groq_fast_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_fast_llm = ChatGroq(
            model=config.GROQ_FAST_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_fast_llm


def _get_vectorstore() -> PineconeVectorStore:
    global _vectorstore
    if _vectorstore is None:
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        index = pc.Index(config.PINECONE_INDEX_NAME)
        _vectorstore = PineconeVectorStore(
            index=index,
            embedding=MiniLMEmbeddings(),
            text_key="text",
        )
    return _vectorstore


def _get_vectorstore_es() -> PineconeVectorStore | None:
    """Multilingual vectorstore (BGE-M3, agroar-prod-multilingual). Returns None if unavailable."""
    global _vectorstore_es
    if _vectorstore_es is _VECTORSTORE_ES_UNAVAILABLE:
        return None
    if _vectorstore_es is None:
        try:
            pc = Pinecone(api_key=config.PINECONE_API_KEY)
            index = pc.Index(config.PINECONE_MULTILINGUAL_INDEX_NAME)
            _vectorstore_es = PineconeVectorStore(
                index=index,
                embedding=BGEEmbeddings(),
                text_key="text",
            )
        except Exception:
            logger.warning(
                "Multilingual vectorstore unavailable — falling back to EN index",
                exc_info=True,
            )
            _vectorstore_es = _VECTORSTORE_ES_UNAVAILABLE
            return None
    return _vectorstore_es


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_PRIMARY_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0.1,
        )
    return _llm


def _advisory_to_verifiable_text(result: AdvisoryResponse) -> str:
    parts: list[str] = [result.problem_summary]
    parts.extend(
        f"{cause.cause}: {cause.explanation}" for cause in result.likely_causes
    )
    parts.extend(result.recommended_actions)
    parts.extend(
        " ".join(filter(None, [
            product.product,
            product.rate,
            product.application_method,
            product.pre_harvest_interval,
        ]))
        for product in result.products_rates
    )
    parts.extend(result.warnings)
    return " ".join(p for p in parts if p)


async def _postprocess_async(
    result: AdvisoryResponse,
    docs: list,
    soil: dict,
    weather: dict,
    county_fips: str,
) -> AdvisoryResponse:
    """Apply citation guard (title-match + NLI) and stamp context_meta."""
    # Step 1: existing title-match citation guard
    retrieved_titles = {
        doc.metadata.get("document_title", "").lower() for doc in docs
    }
    valid_citations = [
        c for c in result.citations
        if c.document_title.lower() in retrieved_titles
    ]
    if not valid_citations:
        result = result.model_copy(update={"confidence": "Low"})
    else:
        result = result.model_copy(update={"citations": valid_citations})

    # Step 2: stamp context_meta
    result = result.model_copy(update={
        "context_meta": result.context_meta.model_copy(update={
            "soil_data_available": soil.get("available", False),
            "weather_data_available": weather.get("available", False),
            "county_fips": county_fips,
        })
    })

    # Step 3: NLI claim verification. This can be disabled for constrained
    # runtimes, but defaults on so confidence scoring remains active.
    if not config.NLI_CITATION_GUARD_ENABLED:
        return result

    answer_prose = _advisory_to_verifiable_text(result)
    retrieved_chunks = [
        {
            "snippet": (doc.page_content or "")[:500] if hasattr(doc, "page_content")
                       else doc.get("snippet", ""),
        }
        for doc in docs
    ]

    nli_result = await citation_guard_v2.verify_answer(answer_prose, retrieved_chunks)
    confidence_score: float = nli_result["confidence_score"]
    claim_verification = nli_result["claim_verification"]

    escalation = None
    if confidence_score < citation_guard_v2.ESCALATION_THRESHOLD:
        escalation = citation_guard_v2.escalation_cue(county_fips)

    update: dict = {
        "confidence_score": confidence_score,
        "claim_verification": claim_verification,
        "escalation": escalation,
    }

    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        escalation_msg = escalation or "Please contact your local UA Extension office."
        update.update({
            "problem_summary": "",
            "likely_causes": [],
            "recommended_actions": [],
            "products_rates": [],
            "warnings": [escalation_msg],
        })

    return result.model_copy(update=update)


async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,
    detected_lang: str = "en",
) -> tuple[AdvisoryResponse, list[dict]]:
    """Returns (advisory, retrieved_chunks)."""
    context_task = asyncio.create_task(get_context(county_fips))

    namespace = CATEGORY_TO_NAMESPACE.get(category)
    # Route to multilingual index for Spanish queries; fall back to EN if unavailable
    if detected_lang == "es":
        vectorstore = _get_vectorstore_es() or _get_vectorstore()
    else:
        vectorstore = _get_vectorstore()

    # When reranking, pull a wider candidate set then trim to TOP_K_RETRIEVAL.
    fetch_k = config.RERANK_CANDIDATES if config.RERANK_ENABLED else config.TOP_K_RETRIEVAL
    retriever_kwargs = {"k": fetch_k}
    if namespace:
        retriever_kwargs["namespace"] = namespace

    docs = await asyncio.to_thread(
        vectorstore.similarity_search,
        message,
        **retriever_kwargs,
    )

    if config.RERANK_ENABLED and docs:
        from services import reranker
        docs = await asyncio.to_thread(
            reranker.rerank, message, docs, config.TOP_K_RETRIEVAL
        )

    ctx = await context_task
    soil = ctx["soil"]
    weather = ctx["weather"]

    # AWD context injection for rice queries with registered fields
    awd_context: str | None = None
    if rice_fields and category == "IN_SCOPE_RICE":
        try:
            from services import awd_scheduler
            from services.context import fetch_usgs_well
            usgs = await fetch_usgs_well(county_fips)
            stress = (usgs or {}).get("stress_level", "normal")
            well_m = (usgs or {}).get("current_depth_m")
            drainage = soil.get("drainage_class") or "default"

            awd_results = []
            for f in rice_fields[:3]:
                if not f.get("field_name") or not f.get("last_flood_date"):
                    continue
                try:
                    flood_date = _date.fromisoformat(f["last_flood_date"])
                except ValueError:
                    continue
                awd_results.append(
                    awd_scheduler.compute_awd_stage(
                        field_name=f["field_name"],
                        last_flood_date=flood_date,
                        drainage_class=drainage,
                        current_well_m=well_m,
                        aquifer_stress_level=stress,
                    )
                )
            if awd_results:
                awd_context = awd_scheduler.format_awd_context(awd_results)
        except Exception:
            logger.warning("AWD context injection failed", exc_info=True)

    county_info = get_county_info(county_fips)
    county_name = county_info["county_name"] if county_info else county_fips

    system_prompt = build_system_prompt(
        soil_context=soil,
        weather_context=weather,
        retrieved_docs=docs,
        session_history=session_history,
        language=language,
        is_safety_critical=(category == "SAFETY_CRITICAL"),
        county_name=county_name,
        awd_context=awd_context,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message),
    ]

    # Provider order from config (default Groq primary — Gemini free is 20/day).
    # Chain 70b -> 8b-instant -> Gemini: when 70b hits its free tokens-per-day cap,
    # 8b (far higher TPD) keeps the pilot serving instead of failing.
    groq = _get_groq_llm()
    groq_fast = _get_groq_fast_llm()
    gemini = _get_llm()
    ordered = ([groq, groq_fast, gemini] if config.LLM_PRIMARY == "groq"
               else [gemini, groq, groq_fast])

    result = None
    last_err = None
    for llm in ordered:
        if llm is None:
            continue
        try:
            result = await llm.with_structured_output(AdvisoryResponse).ainvoke(messages)
            break
        except Exception as e:
            last_err = e
            logger.warning("Generation provider failed, trying next: %s", str(e)[:200])

    if result is None:
        raise RuntimeError(f"RAG generation failed (all providers): {last_err}") from last_err

    advisory = await _postprocess_async(result, docs, soil, weather, county_fips)
    retrieved_chunks = [
        {
            "document_title": d.metadata.get("document_title", ""),
            "section_heading": d.metadata.get("section_heading", ""),
            "snippet": (d.page_content or "")[:500],
        }
        for d in docs
    ]
    return advisory, retrieved_chunks
