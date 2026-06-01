"""Session and message CRUD. Uses the service-role Supabase client (bypasses RLS).
Always filter by user_id manually in read operations to prevent cross-user data leaks."""
from datetime import datetime, timezone
from services.user import _get_service_client
from utils.db import _assert_insert


def create_session(user_id: str, preview: str) -> dict:
    result = _get_service_client().table("chat_sessions").insert({
        "user_id": user_id,
        "preview": preview[:100].strip(),
    }).execute()
    _assert_insert(result, f"session (user {user_id})")
    return result.data[0]


def get_sessions(user_id: str, limit: int = 20) -> list[dict]:
    result = (
        _get_service_client()
        .table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("last_message_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def add_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    content_type: str,
    retrieved_chunks: list[dict] | None = None,
    confidence_score: float | None = None,
    escalated: bool | None = None,
) -> dict:
    client = _get_service_client()
    row = {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "content_type": content_type,
    }
    if retrieved_chunks is not None:
        row["retrieved_chunks"] = retrieved_chunks
    if confidence_score is not None:
        row["confidence_score"] = confidence_score
    if escalated is not None:
        row["escalated"] = escalated
    result = client.table("chat_messages").insert(row).execute()
    _assert_insert(result, f"message (session {session_id})")
    now = datetime.now(timezone.utc).isoformat()
    client.table("chat_sessions").update({
        "last_message_at": now,
    }).eq("id", session_id).execute()
    return result.data[0]


def get_messages(session_id: str, user_id: str) -> list[dict] | None:
    client = _get_service_client()
    # Manual user_id check because service client bypasses RLS
    ownership = (
        client.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if ownership.data is None:
        return None  # not found or not owned by this user
    result = (
        client.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def delete_session(session_id: str, user_id: str) -> bool:
    client = _get_service_client()
    # Manual user_id check because service client bypasses RLS
    result = (
        client.table("chat_sessions")
        .delete()
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(result.data)
