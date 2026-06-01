"""Shared LLM provider utilities — lazy singletons for the fast/classifier tier.

These serve classification, claim decomposition, and translation (GROQ_FAST_MODEL +
GEMINI_CLASSIFIER_MODEL). Generation uses its own providers in services/rag.py.
"""
import config

_groq = None
_gemini = None


def _is_quota_error(e: Exception) -> bool:
    """True for rate-limit / quota-exhaustion errors that warrant a provider
    fallback. Other errors (auth, schema, bugs) should surface, not be masked."""
    s = str(e).lower()
    return any(t in s for t in (
        "resource_exhausted", "429", "rate limit", "rate_limit",
        "tokens per day", "quota",
    ))


def _get_groq():
    global _groq
    if _groq is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq = ChatGroq(model=config.GROQ_FAST_MODEL, api_key=config.GROQ_API_KEY, temperature=0)
    return _groq


def _get_gemini():
    global _gemini
    if _gemini is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _gemini = ChatGoogleGenerativeAI(
            model=config.GEMINI_CLASSIFIER_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0,
        )
    return _gemini


def _providers():
    if config.LLM_PRIMARY == "local":
        from services.local_llm import get_local_chat
        return [get_local_chat()]
    return ([_get_groq(), _get_gemini()] if config.LLM_PRIMARY == "groq"
            else [_get_gemini(), _get_groq()])
