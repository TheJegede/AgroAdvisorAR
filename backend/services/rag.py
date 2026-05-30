"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
import logging
from datetime import date as _date
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryDraft, AdvisoryResponse
from services.embedding import MiniLMEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
from utils.crops import CROP_NAMESPACES
from services import citation_guard_v2
from utils.prompt import build_system_prompt
from utils.counties import get_county_info
import config

logger = logging.getLogger(__name__)


def _is_quota_error(e: Exception) -> bool:
    """True for rate-limit / quota-exhaustion errors that warrant a provider
    fallback. Other errors (auth, schema, bugs) should surface, not be masked by
    silently trying the next provider."""
    s = str(e).lower()
    return any(t in s for t in (
        "resource_exhausted", "429", "rate limit", "rate_limit",
        "tokens per day", "quota",
    ))


_vectorstore: PineconeVectorStore | None = None
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


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_PRIMARY_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0.1,
        )
    return _llm


def _namespaces_for(category: str) -> list[str]:
    """Pinecone namespaces to search for a classifier category.

    A specific crop → its single namespace. IN_SCOPE_GENERAL_AG maps to None in
    CATEGORY_TO_NAMESPACE; the corpus has no `general`/default namespace (all
    20k vectors live under rice/soybeans/poultry), so a general-ag query must
    fan out across every crop namespace. Previously None meant "pass no namespace",
    which made Pinecone search the empty default namespace → zero docs → every
    general-ag answer suppressed.
    """
    ns = CATEGORY_TO_NAMESPACE.get(category)
    return [ns] if ns else list(CROP_NAMESPACES.values())


def _fanout_search(vectorstore, query: str, k: int, namespaces: list[str]) -> list:
    """Retrieve top-k across one or more namespaces, merged by similarity score.

    Pinecone queries a single namespace per call, so multi-namespace retrieval
    means querying each, then merging by descending cosine score and trimming to k.
    """
    scored: list = []
    for ns in namespaces:
        scored.extend(vectorstore.similarity_search_with_score(query, k=k, namespace=ns))
    scored.sort(key=lambda doc_score: doc_score[1], reverse=True)
    return [doc for doc, _ in scored[:k]]


def _advisory_to_verifiable_text(result: AdvisoryResponse) -> str:
    """Concatenate the SUBSTANTIVE factual claims for NLI grounding.

    Excludes `warnings` on purpose: they are generic safety boilerplate ("consult
    a professional", "follow label directions") that rarely entails from an
    extension passage. Including them (added during F1) tanked the grounding
    score and caused good answers to be suppressed.
    """
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
    return " ".join(p for p in parts if p)


async def _postprocess_async(
    result: AdvisoryDraft | AdvisoryResponse,
    docs: list,
    soil: dict,
    weather: dict,
    county_fips: str,
) -> AdvisoryResponse:
    """Apply citation guard (title-match + NLI) and stamp context_meta.

    Accepts the LLM-authored AdvisoryDraft and promotes it to a full
    AdvisoryResponse (guard fields default None until filled below)."""
    if not isinstance(result, AdvisoryResponse):
        result = AdvisoryResponse(**result.model_dump())
    # Step 1: title-match citation guard.
    # Only meaningful when retrieval carries `document_title` metadata. The gte
    # index (agroar-prod-gte) stores only {text, namespace} — no titles — so this
    # guard can validate NO citation there and would force every grounded answer
    # to Low (NLI 0.34/0.54 notwithstanding). When no retrieved doc carries a
    # title, skip the title guard entirely and let the NLI confidence_score
    # (Step 3) govern. Re-enable fully once gte is re-ingested with title/section
    # metadata (fix 1B).
    titles_present = any(doc.metadata.get("document_title") for doc in docs)
    if titles_present:
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
) -> tuple[AdvisoryResponse, list[dict]]:
    """Returns (advisory, retrieved_chunks)."""
    context_task = asyncio.create_task(get_context(county_fips))

    vectorstore = _get_vectorstore()
    namespaces = _namespaces_for(category)

    # When reranking, pull a wider candidate set then trim to TOP_K_RETRIEVAL.
    fetch_k = config.RERANK_CANDIDATES if config.RERANK_ENABLED else config.TOP_K_RETRIEVAL

    docs = await asyncio.to_thread(
        _fanout_search, vectorstore, message, fetch_k, namespaces,
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
    if config.LLM_PRIMARY == "local":
        from services.local_llm import get_local_chat
        ordered = [get_local_chat()]
    else:
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
            result = await llm.with_structured_output(AdvisoryDraft).ainvoke(messages)
            break
        except Exception as e:
            last_err = e
            # Only fall back on quota/rate-limit. Real errors (auth, schema, bug)
            # must surface, not be masked by trying every provider in turn.
            if not _is_quota_error(e):
                raise
            logger.warning("Generation provider quota-exhausted, trying next: %s", str(e)[:200])

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
