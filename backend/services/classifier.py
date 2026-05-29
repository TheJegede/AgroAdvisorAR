"""Query classifier — routes to correct RAG namespace or short-circuits out-of-scope."""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langdetect import detect, LangDetectException
from langdetect import DetectorFactory as _DF
_DF.seed = 0  # deterministic detection across all calls
import config
from utils.crops import CROP_NAMESPACES, CROP_POULTRY, CROP_RICE, CROP_SOYBEANS

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

# Specific crop categories — eligible for follow-up inheritance
SPECIFIC_CROP_CATEGORIES = {"IN_SCOPE_RICE", "IN_SCOPE_SOYBEANS", "IN_SCOPE_POULTRY"}
# Ambiguous follow-up threshold (word count)
_FOLLOWUP_WORD_LIMIT = 8


def detect_language(text: str) -> str:
    """Return 'es' if text is Spanish, 'en' for everything else.

    Defaults to 'en' on detection failure (empty, too-short, or ambiguous text).
    """
    if not text or not text.strip():
        return "en"
    try:
        return "es" if detect(text) == "es" else "en"
    except LangDetectException:
        return "en"


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
    "IN_SCOPE_RICE": CROP_NAMESPACES[CROP_RICE],
    "IN_SCOPE_SOYBEANS": CROP_NAMESPACES[CROP_SOYBEANS],
    "IN_SCOPE_POULTRY": CROP_NAMESPACES[CROP_POULTRY],
    "IN_SCOPE_GENERAL_AG": None,  # None = search all namespaces
}


async def classify_query(message: str, last_category: str | None = None) -> str:
    prompt = CLASSIFIER_PROMPT.format(message=message)
    llm = _get_llm()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        category = response.content.strip().upper()
        if category not in CATEGORIES:
            category = "IN_SCOPE_GENERAL_AG"
    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            try:
                groq = _get_groq_llm()
                if groq:
                    response = await groq.ainvoke([HumanMessage(content=prompt)])
                    category = response.content.strip().upper()
                    if category not in CATEGORIES:
                        category = "IN_SCOPE_GENERAL_AG"
                else:
                    category = "IN_SCOPE_GENERAL_AG"
            except Exception:
                category = "IN_SCOPE_GENERAL_AG"
        else:
            raise

    # Inherit last crop context for short, ambiguous follow-ups
    if (
        category == "IN_SCOPE_GENERAL_AG"
        and last_category in SPECIFIC_CROP_CATEGORIES
        and len(message.split()) <= _FOLLOWUP_WORD_LIMIT
    ):
        return last_category

    return category
