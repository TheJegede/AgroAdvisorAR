"""Admin-only endpoints: dashboard metrics + human eval queue + scoring."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from services.admin import (
    require_admin,
    get_dashboard_metrics,
    get_eval_queue,
    submit_score,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class ScoreRequest(BaseModel):
    message_id: str
    accuracy_score: int = Field(ge=1, le=5)
    correction: str | None = Field(default=None, max_length=2000)


@router.get("/metrics")
def admin_metrics(_: dict = Depends(require_admin)):
    return get_dashboard_metrics()


@router.get("/eval/queue")
def admin_eval_queue(
    filter: Literal["flagged", "spotcheck", "all"] = Query(default="flagged"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_admin),
):
    return get_eval_queue(
        evaluator_id=user["sub"],
        filter_=filter,
        limit=limit,
        offset=offset,
    )


@router.post("/eval/score", status_code=201)
def admin_submit_score(req: ScoreRequest, user: dict = Depends(require_admin)):
    row = submit_score(
        message_id=req.message_id,
        evaluator_id=user["sub"],
        accuracy_score=req.accuracy_score,
        correction=req.correction,
    )
    return {
        "id": row["id"],
        "message_id": row["message_id"],
        "accuracy_score": row["accuracy_score"],
        "created_at": row["created_at"],
    }
