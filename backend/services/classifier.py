"""Query classifier — routes to correct RAG namespace or short-circuits out-of-scope."""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import config

_groq_llm = None


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(
            model=config.GROQ_CLASSIFIER_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0,
        )
    return _groq_llm

CATEGORIES = {
    "IN_SCOPE_RICE",
    "IN_SCOPE_SOYBEANS",
    "IN_SCOPE_POULTRY",
    "IN_SCOPE_GENERAL_AG",
    "OUT_OF_SCOPE",
    "SAFETY_CRITICAL",
}

CLASSIFIER_PROMPT = """Classify this farmer query into exactly one category:
- IN_SCOPE_RICE
- IN_SCOPE_SOYBEANS
- IN_SCOPE_POULTRY
- IN_SCOPE_GENERAL_AG
- OUT_OF_SCOPE
- SAFETY_CRITICAL

SAFETY_CRITICAL: queries about pesticide mixing, chemical overdose, toxic exposure, or regulatory violations.
OUT_OF_SCOPE: any non-agricultural topic.

Query: {message}
Return ONLY the category string. No explanation."""

_llm: ChatGoogleGenerativeAI | None = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_CLASSIFIER_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0,
        )
    return _llm


# Maps classifier output → Pinecone namespace
CATEGORY_TO_NAMESPACE = {
    "IN_SCOPE_RICE": "rice",
    "IN_SCOPE_SOYBEANS": "soybeans",
    "IN_SCOPE_POULTRY": "poultry",
    "IN_SCOPE_GENERAL_AG": None,  # None = search all namespaces
}


async def classify_query(message: str) -> str:
    prompt = CLASSIFIER_PROMPT.format(message=message)
    llm = _get_llm()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        category = response.content.strip().upper()
        if category not in CATEGORIES:
            return "IN_SCOPE_GENERAL_AG"
        return category
    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            try:
                groq = _get_groq_llm()
                if groq:
                    response = await groq.ainvoke([HumanMessage(content=prompt)])
                    category = response.content.strip().upper()
                    return category if category in CATEGORIES else "IN_SCOPE_GENERAL_AG"
            except Exception:
                pass
            return "IN_SCOPE_GENERAL_AG"
        raise
