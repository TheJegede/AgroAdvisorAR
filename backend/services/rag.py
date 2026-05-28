"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
from datetime import date as _date
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryResponse
from services.embedding import MiniLMEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
from services import citation_guard_v2
from utils.prompt import build_system_prompt
from utils.counties import get_county_info
import config

_vectorstore: PineconeVectorStore | None = None
_llm: ChatGoogleGenerativeAI | None = None
_groq_llm = None


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(
            model=config.GROQ_CLASSIFIER_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_llm


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

    # Step 3: NLI claim verification
    answer_prose = " ".join(filter(None, [
        result.problem_summary,
        " ".join(result.recommended_actions),
    ]))
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

    namespace = CATEGORY_TO_NAMESPACE.get(category)
    vectorstore = _get_vectorstore()

    retriever_kwargs = {"k": config.TOP_K_RETRIEVAL}
    if namespace:
        retriever_kwargs["namespace"] = namespace

    docs = await asyncio.to_thread(
        vectorstore.similarity_search,
        message,
        **retriever_kwargs,
    )

    ctx = await context_task
    soil = ctx["soil"]
    weather = ctx["weather"]

    # AWD context injection for rice queries with registered fields
    awd_context: str | None = None
    if rice_fields and category == "IN_SCOPE_RICE":
        from services import awd_scheduler
        from services.context import fetch_usgs_well
        usgs = await fetch_usgs_well(county_fips)
        stress = (usgs or {}).get("stress_level", "normal")
        well_m = (usgs or {}).get("current_depth_m")
        drainage = soil.get("drainage_class") or "default"

        awd_results = [
            awd_scheduler.compute_awd_stage(
                field_name=f["field_name"],
                last_flood_date=_date.fromisoformat(f["last_flood_date"]),
                drainage_class=drainage,
                current_well_m=well_m,
                aquifer_stress_level=stress,
            )
            for f in rice_fields[:3]
            if f.get("field_name") and f.get("last_flood_date")
        ]
        if awd_results:
            awd_context = awd_scheduler.format_awd_context(awd_results)

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

    structured_llm = _get_llm().with_structured_output(AdvisoryResponse)

    result = None
    last_err = None
    for attempt in range(2):
        try:
            result = await structured_llm.ainvoke(messages)
            break
        except Exception as e:
            last_err = e
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                try:
                    groq = _get_groq_llm()
                    if groq:
                        result = await groq.with_structured_output(AdvisoryResponse).ainvoke(messages)
                        break
                except Exception as groq_err:
                    last_err = groq_err
                break
            if attempt == 1:
                raise RuntimeError(f"Structured output failed after 2 attempts: {e}") from e

    if result is None:
        raise RuntimeError(f"RAG generation failed: {last_err}") from last_err

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
