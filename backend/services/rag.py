"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryResponse
from services.embedding import MiniLMEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
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
            text_key="text",  # must match embedder.py metadata key
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


def _postprocess(
    result: AdvisoryResponse,
    docs: list,
    soil: dict,
    weather: dict,
    county_fips: str,
) -> AdvisoryResponse:
    """Apply citation guard and stamp context_meta onto a raw LLM result."""
    retrieved_titles = {
        doc.metadata.get("document_title", "").lower() for doc in docs
    }
    valid_citations = [
        c for c in result.citations
        if c.document_title.lower() in retrieved_titles
    ]
    if not valid_citations:
        # Keep originals but downgrade confidence — no retrieved doc supports them
        result = result.model_copy(update={"confidence": "Low"})
    else:
        result = result.model_copy(update={"citations": valid_citations})

    return result.model_copy(update={
        "context_meta": result.context_meta.model_copy(update={
            "soil_data_available": soil.get("available", False),
            "weather_data_available": weather.get("available", False),
            "county_fips": county_fips,
        })
    })


async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
) -> AdvisoryResponse:
    # Fetch context and retrieve docs concurrently
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
                # Gemini quota exhausted — try Groq immediately (skip second Gemini attempt)
                try:
                    groq = _get_groq_llm()
                    if groq:
                        result = await groq.with_structured_output(AdvisoryResponse).ainvoke(messages)
                        break
                except Exception as groq_err:
                    last_err = groq_err
                break  # don't retry Gemini if quota is gone
            if attempt == 1:
                raise RuntimeError(f"Structured output failed after 2 attempts: {e}") from e

    if result is None:
        raise RuntimeError(f"RAG generation failed: {last_err}") from last_err

    return _postprocess(result, docs, soil, weather, county_fips)
