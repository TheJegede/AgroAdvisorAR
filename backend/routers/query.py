"""POST /api/v1/query — core query endpoint with SSE streaming."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.classifier import classify_query
from services.rag import run_rag_query
from services.translation import translate_to_en, translate_advisory_to_es
from services.session import add_message as save_message
from services.user import get_profile
from services.cache import rate_limit_hit
from services.sanitizer import sanitize, InjectionDetected
from utils.prompt import out_of_scope_message
import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Fixed-window query rate limit per authenticated user (see cache.rate_limit_hit).
QUERY_WINDOW_SECONDS = 3600


class QueryRequest(BaseModel):
    message: str
    language: str = "en"
    session_history: list[dict] = Field(default_factory=list)
    session_id: str | None = None
    last_category: str | None = None


class OutOfScopeResponse(BaseModel):
    message: str
    category: str
    message_id: str | None = None  # populated when session_id provided


async def maybe_translate_query(message: str, language: str, user_id: str | None = None) -> str:
    """ES bridge: translate the query to English so the all-English pipeline runs.
    EN passes through unchanged."""
    if language == "es":
        return await translate_to_en(message, user_id=user_id)
    return message


@router.post("/query")
async def query(req: QueryRequest, user: dict = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    if len(req.message) > 800:
        raise HTTPException(status_code=400, detail="message exceeds 800 character limit")

    # Rate limit before any LLM call to cap free-tier abuse.
    allowed, _remaining = rate_limit_hit(
        f"query_throttle:{user['sub']}",
        config.RATE_LIMIT_PER_HOUR,
        QUERY_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You have reached the {config.RATE_LIMIT_PER_HOUR}-queries-per-hour "
                "limit. Please try again later."
            ),
            headers={"Retry-After": str(QUERY_WINDOW_SECONDS)},
        )

    # Strip / reject prompt-injection attempts before the message reaches the
    # classifier and RAG chain. Mutates req.message to the sanitized form.
    try:
        req.message = sanitize(req.message)
    except InjectionDetected as e:
        raise HTTPException(status_code=400, detail=str(e))

    profile = get_profile(user["sub"])
    county_fips = (profile or {}).get("county_fips") or config.DEFAULT_COUNTY_FIPS
    rice_fields = (profile or {}).get("rice_fields") or []
    language = req.language

    # Translate-bridge: ES query -> EN so the whole RAG pipeline runs in English.
    en_message = await maybe_translate_query(req.message, language, user_id=user["sub"])
    category = await classify_query(en_message, last_category=req.last_category, user_id=user["sub"])

    if category == "OUT_OF_SCOPE":
        oos_message = out_of_scope_message(language)
        out_of_scope_message_id: str | None = None
        if req.session_id:
            try:
                save_message(req.session_id, user["sub"], "user", req.message, "text")
                oos_row = save_message(
                    req.session_id, user["sub"], "assistant",
                    oos_message, "oos",
                )
                out_of_scope_message_id = oos_row["id"]
            except Exception:
                logger.exception("Failed to persist out-of-scope query response")
        return OutOfScopeResponse(
            message=oos_message,
            category=category,
            message_id=out_of_scope_message_id,
        )

    async def event_stream():
        try:
            result, retrieved_chunks = await run_rag_query(
                message=en_message,
                county_fips=county_fips,
                language="en",
                category=category,
                session_history=req.session_history,
                rice_fields=rice_fields,
                user_id=user["sub"],
            )
            if language == "es":
                result = await translate_advisory_to_es(result, user_id=user["sub"])

            assistant_message_id: str | None = None
            if req.session_id:
                try:
                    save_message(req.session_id, user["sub"], "user", req.message, "text")
                    assistant_row = save_message(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(result.model_dump(), ensure_ascii=False),
                        "advisory",
                        retrieved_chunks=retrieved_chunks,
                        confidence_score=result.confidence_score,
                        escalated=result.escalation is not None,
                    )
                    assistant_message_id = assistant_row["id"]
                except Exception:
                    logger.exception("Failed to persist advisory query response")

            envelope = {
                "advisory": result.model_dump(),
                "message_id": assistant_message_id,
                "category": category,
            }
            payload = json.dumps(envelope, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
