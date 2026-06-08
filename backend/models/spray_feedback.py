from typing import Literal, Optional
from pydantic import BaseModel, Field


class SprayFeedbackRequest(BaseModel):
    record_id: str
    rating: Literal[-1, 1]
    comment: Optional[str] = Field(default=None, max_length=500)


class SprayFeedbackResponse(BaseModel):
    id: str
    record_id: str
    farmer_id: str
    rating: int
    comment: Optional[str] = None
    created_at: str
