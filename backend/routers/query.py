"""POST /api/v1/query — core query endpoint with SSE streaming."""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.auth import get_current_user
from services.classifier import classify_query
from services.rag import run_rag_query
from services.session import add_message as save_message
from services.user import get_profile
from utils.prompt import OUT_OF_SCOPE_MESSAGE

router = APIRouter()


class QueryRequest(BaseModel):
    message: str
    language: str = "en"
    session_history: list[dict] = []
    session_id: str | None = None


class OutOfScopeResponse(BaseModel):
    message: str
    category: str
    message_id: str | None = None  # populated when session_id provided


@router.post("/query")
async def query(req: QueryRequest, user: dict = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    if len(req.message) > 800:
        raise HTTPException(status_code=400, detail="message exceeds 800 character limit")

    profile = get_profile(user["sub"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Farmer profile not found. Please complete registration.")

    county_fips = profile["county_fips"]
    language = req.language

    category = await classify_query(req.message)

    if category == "OUT_OF_SCOPE":
        oos_message_id: str | None = None
        if req.session_id:
            try:
                save_message(req.session_id, user["sub"], "user", req.message, "text")
                oos_row = save_message(
                    req.session_id, user["sub"], "assistant",
                    OUT_OF_SCOPE_MESSAGE, "oos",
                )
                oos_message_id = oos_row["id"]
            except Exception:
                pass  # persistence failure must never break the response
        return OutOfScopeResponse(
            message=OUT_OF_SCOPE_MESSAGE,
            category=category,
            message_id=oos_message_id,
        )

    async def event_stream():
        try:
            result, retrieved_chunks = await run_rag_query(
                message=req.message,
                county_fips=county_fips,
                language=language,
                category=category,
                session_history=req.session_history,
            )

            assistant_message_id: str | None = None
            if req.session_id:
                try:
                    save_message(req.session_id, user["sub"], "user", req.message, "text")
                    assistant_row = save_message(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(result.model_dump(), ensure_ascii=False),
                        "advisory",
                        retrieved_chunks=retrieved_chunks,
                    )
                    assistant_message_id = assistant_row["id"]
                except Exception:
                    pass  # persistence failure must never break the advisory response

            envelope = {
                "advisory": result.model_dump(),
                "message_id": assistant_message_id,
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
