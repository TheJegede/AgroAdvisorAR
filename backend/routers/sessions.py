"""GET /sessions, POST /sessions, GET /sessions/{session_id}/messages"""
from fastapi import APIRouter, Depends, HTTPException
from models.session import (
    SessionCreate, SessionResponse, SessionListResponse,
    MessageListResponse, MessageResponse,
)
from services.auth import get_current_user
from services.session import create_session, get_sessions, get_messages, delete_session

router = APIRouter()


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(user: dict = Depends(get_current_user)):
    rows = get_sessions(user["sub"])
    return SessionListResponse(sessions=[SessionResponse(**r) for r in rows])


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def new_session(req: SessionCreate, user: dict = Depends(get_current_user)):
    row = create_session(user["sub"], req.preview)
    return SessionResponse(**row)


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
def list_messages(session_id: str, user: dict = Depends(get_current_user)):
    rows = get_messages(session_id, user["sub"])
    if rows is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return MessageListResponse(messages=[MessageResponse(**r) for r in rows])


@router.delete("/sessions/{session_id}", status_code=204)
def remove_session(session_id: str, user: dict = Depends(get_current_user)):
    success = delete_session(session_id, user["sub"])
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
