"""Pydantic schemas for /feedback endpoint."""
from pydantic import BaseModel, Field
from typing import Literal


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: int
    created_at: str
