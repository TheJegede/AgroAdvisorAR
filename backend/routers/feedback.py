"""POST /api/v1/feedback — thumbs up/down + optional comment per assistant message."""
from fastapi import APIRouter, Depends, HTTPException
from models.feedback import FeedbackRequest, FeedbackResponse
from services.auth import get_current_user
from services.feedback import (
    check_rate_limit,
    verify_message_ownership,
    insert_feedback,
    FEEDBACK_WINDOW_SECONDS,
)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def submit_feedback(
    req: FeedbackRequest,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]

    allowed, _ = check_rate_limit(user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many feedback submissions. Please try again later.",
            headers={"Retry-After": str(FEEDBACK_WINDOW_SECONDS)},
        )

    if not verify_message_ownership(req.message_id, user_id):
        raise HTTPException(
            status_code=404,
            detail="Message not found or does not belong to this user.",
        )

    row = insert_feedback(
        message_id=req.message_id,
        user_id=user_id,
        rating=req.rating,
        comment=req.comment,
    )

    return FeedbackResponse(
        id=row["id"],
        message_id=row["message_id"],
        rating=row["rating"],
        created_at=row["created_at"],
    )
