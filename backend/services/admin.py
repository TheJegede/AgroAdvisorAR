"""Admin dashboard + human-eval queue. Service-role client bypasses RLS —
all reads/writes happen with the admin's permission inherited from the
require_admin dependency, never directly from user JWT claims."""
import json
import random
from fastapi import Depends, HTTPException, status
from services.auth import get_current_user
from services.user import _get_service_client
import config

# Cap queue page size to avoid huge payloads when evaluator scrolls.
MAX_QUEUE_LIMIT = 50


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — enforce that caller is in ADMIN_USER_IDS allowlist."""
    if user["sub"] not in config.ADMIN_USER_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user


def _scored_message_ids(evaluator_id: str) -> set[str]:
    """Set of message_ids the current evaluator has already scored at least once.
    Multiple evaluators score independently, so the queue is per-evaluator."""
    result = (
        _get_service_client()
        .table("human_eval_scores")
        .select("message_id")
        .eq("evaluator_id", evaluator_id)
        .execute()
    )
    return {r["message_id"] for r in (result.data or [])}


def _hydrate_messages(rows: list[dict]) -> list[dict]:
    """Parse advisory content JSON and attach the latest rating per message."""
    if not rows:
        return []

    message_ids = [r["id"] for r in rows]
    fb_result = (
        _get_service_client()
        .table("response_feedback")
        .select("message_id, rating, comment, created_at")
        .in_("message_id", message_ids)
        .order("created_at", desc=True)
        .execute()
    )
    latest_feedback: dict[str, dict] = {}
    for fb in fb_result.data or []:
        latest_feedback.setdefault(fb["message_id"], fb)

    hydrated = []
    for row in rows:
        parsed_content: dict | str
        if row.get("content_type") == "advisory" and row.get("content"):
            try:
                parsed_content = json.loads(row["content"])
            except Exception:
                parsed_content = row["content"]
        else:
            parsed_content = row.get("content")

        hydrated.append({
            "id": row["id"],
            "session_id": row.get("session_id"),
            "content_type": row.get("content_type"),
            "content": parsed_content,
            "retrieved_chunks": row.get("retrieved_chunks") or [],
            "created_at": row.get("created_at"),
            "latest_feedback": latest_feedback.get(row["id"]),
        })
    return hydrated


def get_eval_queue(
    evaluator_id: str,
    filter_: str = "flagged",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Returns assistant messages awaiting evaluator review.

    - flagged:   messages with at least one thumbs-down, not yet scored by this evaluator
    - spotcheck: random sample of unscored assistant messages regardless of rating
    - all:       flagged first, then spotcheck filler
    """
    limit = max(1, min(limit, MAX_QUEUE_LIMIT))
    scored = _scored_message_ids(evaluator_id)
    client = _get_service_client()

    flagged_messages: list[dict] = []
    if filter_ in ("flagged", "all"):
        # Pull recent thumbs-down feedback, then load underlying assistant messages.
        # Over-fetch to allow filtering already-scored ones without paging again.
        fb_rows = (
            client.table("response_feedback")
            .select("message_id, created_at")
            .eq("rating", -1)
            .order("created_at", desc=True)
            .limit(limit * 4 + offset)
            .execute()
        ).data or []

        seen: set[str] = set()
        candidate_ids: list[str] = []
        for fb in fb_rows:
            mid = fb["message_id"]
            if mid in seen or mid in scored:
                continue
            seen.add(mid)
            candidate_ids.append(mid)

        # Apply offset + limit at the message level (not at feedback level).
        page_ids = candidate_ids[offset:offset + limit]
        if page_ids:
            msg_result = (
                client.table("chat_messages")
                .select("*")
                .in_("id", page_ids)
                .eq("role", "assistant")
                .execute()
            )
            # Preserve the flagged ordering (newest negative feedback first).
            id_to_row = {r["id"]: r for r in (msg_result.data or [])}
            flagged_messages = [id_to_row[i] for i in page_ids if i in id_to_row]

    spotcheck_messages: list[dict] = []
    if filter_ in ("spotcheck", "all"):
        remaining = limit - len(flagged_messages) if filter_ == "all" else limit
        if remaining > 0:
            # Random sample of unscored assistant messages. Supabase client lacks
            # native RANDOM(), so pull a recent window and shuffle in memory.
            window_result = (
                client.table("chat_messages")
                .select("*")
                .eq("role", "assistant")
                .in_("content_type", ["advisory", "oos"])
                .order("created_at", desc=True)
                .limit(200)
                .execute()
            )
            window = [
                r for r in (window_result.data or [])
                if r["id"] not in scored
                and r["id"] not in {m["id"] for m in flagged_messages}
            ]
            random.shuffle(window)
            spotcheck_messages = window[:remaining]

    combined = flagged_messages + spotcheck_messages
    return {
        "items": _hydrate_messages(combined),
        "filter": filter_,
        "limit": limit,
        "offset": offset,
        "returned": len(combined),
    }


def submit_score(
    message_id: str,
    evaluator_id: str,
    accuracy_score: int,
    correction: str | None,
) -> dict:
    # Confirm the target message exists and is an assistant turn.
    msg = (
        _get_service_client()
        .table("chat_messages")
        .select("id")
        .eq("id", message_id)
        .eq("role", "assistant")
        .maybe_single()
        .execute()
    )
    if msg.data is None:
        raise HTTPException(status_code=404, detail="Message not found.")

    result = (
        _get_service_client()
        .table("human_eval_scores")
        .insert({
            "message_id": message_id,
            "evaluator_id": evaluator_id,
            "accuracy_score": accuracy_score,
            "correction": correction,
        })
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Score insert returned no data for message {message_id}")
    return result.data[0]


def get_dashboard_metrics() -> dict:
    """Aggregated metrics for the admin dashboard."""
    result = _get_service_client().rpc("get_admin_dashboard_metrics").execute()
    data = result.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise RuntimeError("get_admin_dashboard_metrics RPC returned no payload")
    return data
