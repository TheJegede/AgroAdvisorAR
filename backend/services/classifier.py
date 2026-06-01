"""Query classifier — routes to correct RAG namespace or short-circuits out-of-scope."""
from langchain_core.messages import HumanMessage
import config
from utils.crops import CROP_NAMESPACES, CROP_POULTRY, CROP_RICE, CROP_SOYBEANS
from utils.llm import _is_quota_error, _get_groq, _get_gemini

CATEGORIES = {
    "IN_SCOPE_RICE:DIAG",
    "IN_SCOPE_RICE:INFO",
    "IN_SCOPE_SOYBEANS:DIAG",
    "IN_SCOPE_SOYBEANS:INFO",
    "IN_SCOPE_POULTRY:DIAG",
    "IN_SCOPE_POULTRY:INFO",
    "IN_SCOPE_GENERAL_AG:DIAG",
    "IN_SCOPE_GENERAL_AG:INFO",
    "OUT_OF_SCOPE",
    "SAFETY_CRITICAL",
}

# Specific crop categories — eligible for follow-up inheritance
SPECIFIC_CROP_CATEGORIES = {
    "IN_SCOPE_RICE:DIAG", "IN_SCOPE_RICE:INFO",
    "IN_SCOPE_SOYBEANS:DIAG", "IN_SCOPE_SOYBEANS:INFO",
    "IN_SCOPE_POULTRY:DIAG", "IN_SCOPE_POULTRY:INFO",
}
# Ambiguous follow-up threshold (word count)
_FOLLOWUP_WORD_LIMIT = 8


CLASSIFIER_PROMPT = """Classify this farmer query into exactly one category. If the query falls into one of the agricultural in-scope categories, append either ':DIAG' (if the query is diagnostic, seeking identifying causes, treatment rates, products, or troubleshooting for a specific crop/flock problem or health issue) or ':INFO' (if the query is informational/educational, asking for general practices, explanations, guidelines, or definitions without describing a specific active problem):
- IN_SCOPE_RICE:DIAG
- IN_SCOPE_RICE:INFO
- IN_SCOPE_SOYBEANS:DIAG
- IN_SCOPE_SOYBEANS:INFO
- IN_SCOPE_POULTRY:DIAG
- IN_SCOPE_POULTRY:INFO
- IN_SCOPE_GENERAL_AG:DIAG
- IN_SCOPE_GENERAL_AG:INFO
- OUT_OF_SCOPE
- SAFETY_CRITICAL

SAFETY_CRITICAL: queries about pesticide mixing, chemical overdose, toxic exposure, or regulatory violations.
OUT_OF_SCOPE: any non-agricultural topic.

Query: {message}
Return ONLY the category string (e.g. IN_SCOPE_RICE:INFO). No explanation."""

# Maps classifier output → Pinecone namespace.
# IN_SCOPE_GENERAL_AG → None is resolved by rag._namespaces_for() into a fan-out
# across every crop namespace (the corpus has no `general` namespace). Do NOT read
# None as "no namespace" at the retriever — that searches Pinecone's empty default
# namespace and returns zero docs.
CATEGORY_TO_NAMESPACE = {
    "IN_SCOPE_RICE:DIAG": CROP_NAMESPACES[CROP_RICE],
    "IN_SCOPE_RICE:INFO": CROP_NAMESPACES[CROP_RICE],
    "IN_SCOPE_SOYBEANS:DIAG": CROP_NAMESPACES[CROP_SOYBEANS],
    "IN_SCOPE_SOYBEANS:INFO": CROP_NAMESPACES[CROP_SOYBEANS],
    "IN_SCOPE_POULTRY:DIAG": CROP_NAMESPACES[CROP_POULTRY],
    "IN_SCOPE_POULTRY:INFO": CROP_NAMESPACES[CROP_POULTRY],
    "IN_SCOPE_GENERAL_AG:DIAG": None,
    "IN_SCOPE_GENERAL_AG:INFO": None,
}


async def classify_query(message: str, last_category: str | None = None) -> str:
    prompt = CLASSIFIER_PROMPT.format(message=message)
    # Provider order from config (default Groq primary — Gemini free is 20/day).
    if config.LLM_PRIMARY == "local":
        from services.local_llm import get_local_chat
        ordered = [get_local_chat()]
    else:
        ordered = ([_get_groq(), _get_gemini()] if config.LLM_PRIMARY == "groq"
                   else [_get_gemini(), _get_groq()])
    category = "IN_SCOPE_GENERAL_AG:DIAG"
    for llm in ordered:
        if llm is None:
            continue
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            category = response.content.strip().upper()
            if category not in CATEGORIES:
                # If category is valid but missing suffix, default to DIAG
                if category + ":DIAG" in CATEGORIES:
                    category = category + ":DIAG"
                elif category + ":INFO" in CATEGORIES:
                    category = category + ":INFO"
                else:
                    category = "IN_SCOPE_GENERAL_AG:DIAG"
            break
        except Exception as e:
            # Only swallow quota/rate-limit (fall back, then degrade to
            # GENERAL_AG). Real errors must surface, not silently misroute every
            # query to the all-namespaces path.
            if not _is_quota_error(e):
                raise
            continue

    # Inherit last crop context for short, ambiguous follow-ups
    if (
        category.startswith("IN_SCOPE_GENERAL_AG")
        and last_category in SPECIFIC_CROP_CATEGORIES
        and len(message.split()) <= _FOLLOWUP_WORD_LIMIT
    ):
        return last_category

    return category
