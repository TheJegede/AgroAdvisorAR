"""POST /api/v1/query — core query endpoint with SSE streaming."""
import asyncio
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
from services.session import get_messages
from services.user import get_profile
from services.cache import rate_limit_hit
from services import answer_cache
from services.sanitizer import sanitize, InjectionDetected, MessageTooLong
from utils.prompt import out_of_scope_message
import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Fixed-window query rate limit per authenticated user (see cache.rate_limit_hit).
QUERY_WINDOW_SECONDS = 3600

# User-facing SSE error — never leak raw exception text (provider URLs, internal
# messages, occasional key fragments in langchain errors) to the browser.
GENERIC_STREAM_ERROR = "Something went wrong generating your advisory. Please try again."
TRUSTED_HISTORY_LIMIT = 10
_HISTORY_ROLES = {"user", "assistant"}

# SSE keepalive: yield a comment line this often while the LLM call runs so an
# intermediary proxy (Vercel /api/* rewrite -> HF Space) never sees a silent
# connection. Must stay well under the observed ~6s proxy reap timeout.
HEARTBEAT_INTERVAL_SECONDS = 2


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


def _normalize_history(rows: list[dict], *, sanitize_content: bool) -> list[dict]:
    history: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        if role not in _HISTORY_ROLES:
            continue

        content = str(row.get("content", ""))
        if sanitize_content:
            content = sanitize(content)
        else:
            content = content.strip()
        if not content:
            continue

        history.append({"role": role, "content": content})
    return history[-TRUSTED_HISTORY_LIMIT:]


def _trusted_rag_history(req: QueryRequest, user_id: str) -> list[dict]:
    if req.session_id:
        rows = get_messages(req.session_id, user_id)
        if rows is None:
            return []
        return _normalize_history(rows, sanitize_content=False)

    return _normalize_history(req.session_history, sanitize_content=True)


def _advisory_sse(advisory: dict, message_id, category):
    """Build the SSE generator for a ready advisory dict (cache hit). Same frame
    shape as the miss path so the frontend consumer is unchanged."""
    async def _gen():
        yield ": keepalive\n\n"
        envelope = {"advisory": advisory, "message_id": message_id, "category": category}
        yield f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return _gen()


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
    except (InjectionDetected, MessageTooLong) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        session_history = _trusted_rag_history(req, user["sub"])
    except (InjectionDetected, MessageTooLong) as e:
        raise HTTPException(status_code=400, detail=str(e))

    profile = get_profile(user["sub"])
    county_fips = (profile or {}).get("county_fips") or config.DEFAULT_COUNTY_FIPS
    rice_fields = (profile or {}).get("rice_fields") or []
    language = req.language

    # Translate-bridge: ES query -> EN so the whole RAG pipeline runs in English.
    en_message = await maybe_translate_query(req.message, language, user_id=user["sub"])

    # L3 answer cache: serve a stored reference-safe advisory for a verbatim-repeat,
    # first-turn query — skipping classify/retrieve/generate/guard. First-turn only
    # (cache_key stays None on a follow-up -> no read, no write).
    cache_key = None
    if not session_history:
        cache_key = answer_cache.answer_cache_key(en_message, language, county_fips, rice_fields)
        cached = answer_cache.get_cached_answer(cache_key)
        if cached:
            cached = dict(cached)
            hit_category = cached.pop("_category", None)
            message_id = None
            if req.session_id:
                try:
                    save_message(req.session_id, user["sub"], "user", req.message, "text")
                    row = save_message(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(cached, ensure_ascii=False), "advisory",
                    )
                    message_id = row["id"]
                except Exception:
                    logger.exception("Failed to persist cached advisory")
            return StreamingResponse(
                _advisory_sse(cached, message_id, hit_category),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

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
        # First byte immediately — defeats the proxy first-byte/idle timeout that
        # was reaping the connection at ~6s during the LLM call. Comment lines
        # (starting with ':') are ignored by the SSE client.
        yield ": keepalive\n\n"

        # Stream partial draft tokens for EN first-turn (cache miss) queries only.
        # cache_key is None when session_history is non-empty (follow-up); in that
        # case partial frames would be noisy and wasteful. ES queries skip streaming
        # because partial frames would be in English before the translation step.
        stream = (language == "en" and cache_key is not None)

        progress_q: asyncio.Queue = asyncio.Queue()
        rag_task = asyncio.create_task(
            run_rag_query(
                message=en_message,
                county_fips=county_fips,
                language="en",
                category=category,
                session_history=session_history,
                rice_fields=rice_fields,
                user_id=user["sub"],
                progress=progress_q,
                stream=stream,
            )
        )
        try:
            while True:
                if rag_task.done() and progress_q.empty():
                    break
                try:
                    item = await asyncio.wait_for(progress_q.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
                    if item.get("kind") == "partial":
                        frame = json.dumps({"partial": item["draft"]}, ensure_ascii=False)
                    else:
                        frame = json.dumps({"progress": item}, ensure_ascii=False)
                    yield f"data: {frame}\n\n"
                except asyncio.TimeoutError:
                    if not rag_task.done():
                        yield ": keepalive\n\n"

            result, retrieved_chunks = rag_task.result()
            # Capture the English advisory BEFORE the ES translation — cache
            # eligibility is judged on the English text (English _TIME_SENSITIVE_RE).
            en_advisory_dump = result.model_dump()
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

            # L3 WRITE: cache only first-turn (cache_key set), non-suppressed,
            # reference-safe answers. Stored value is the user-facing advisory (ES
            # if translated) plus _category; eligibility judged on the EN text.
            if cache_key and not getattr(result, "suppressed", False) and answer_cache.is_cacheable_as_reference(en_advisory_dump):
                final_dump = result.model_dump()
                answer_cache.set_cached_answer(cache_key, {**final_dump, "_category": category})

            envelope = {
                "advisory": result.model_dump(),
                "message_id": assistant_message_id,
                "category": category,
            }
            payload = json.dumps(envelope, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            # Client/proxy disconnected — free the in-flight LLM task and let
            # cancellation propagate (do NOT mask as a generic error frame).
            rag_task.cancel()
            raise
        except Exception:
            logger.exception("Query stream failed")
            error_payload = json.dumps({"error": GENERIC_STREAM_ERROR})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            if not rag_task.done():
                rag_task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
