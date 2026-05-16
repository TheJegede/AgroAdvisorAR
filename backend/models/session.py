"""Pydantic schemas for session and message endpoints."""
from pydantic import BaseModel


class SessionCreate(BaseModel):
    preview: str = ""


class SessionResponse(BaseModel):
    id: str
    preview: str
    message_count: int
    created_at: str
    last_message_at: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str          # 'user' | 'assistant'
    content: str       # raw text for user; JSON string for advisory; plain text for oos
    content_type: str  # 'text' | 'advisory' | 'oos'
    created_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
