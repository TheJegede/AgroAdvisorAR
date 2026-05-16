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
    """Aggregated metrics for the admin dashboard.

    Returns counts + breakdowns suitable for charts:
      - totals: registered users, sessions, assistant messages, feedback rows
      - language_split: count of farmer_profiles per language
      - county_query_volume: top counties by assistant message count
      - feedback_distribution: counts of rating=1 vs rating=-1
      - human_eval_summary: count + mean accuracy_score
      - top_user_queries: top 20 verbatim user prompts
      - recent_eval_runs: last 10 automated eval runs (MRR / NDCG over time)
    """
    client = _get_service_client()

    def count(table: str, filters: list[tuple[str, str, str]] | None = None) -> int:
        q = client.table(table).select("id", count="exact")
        for col, op, val in filters or []:
            q = getattr(q, op)(col, val)
        res = q.limit(1).execute()
        return res.count or 0

    totals = {
        "registered_users": count("farmer_profiles"),
        "sessions": count("chat_sessions"),
        "assistant_messages": count("chat_messages", [("role", "eq", "assistant")]),
        "feedback_rows": count("response_feedback"),
    }

    language_rows = (
        client.table("farmer_profiles")
        .select("language")
        .execute()
    ).data or []
    language_split: dict[str, int] = {}
    for r in language_rows:
        language_split[r["language"]] = language_split.get(r["language"], 0) + 1

    county_rows = (
        client.table("farmer_profiles")
        .select("county_fips, county_name")
        .execute()
    ).data or []
    county_by_id = {r["county_fips"]: r["county_name"] for r in county_rows}

    # Assistant-message volume per county: join via user_id → farmer_profiles.county_fips
    user_to_county = {r.get("id"): r.get("county_fips") for r in (
        client.table("farmer_profiles").select("id, county_fips").execute()
    ).data or []}
    asst_rows = (
        client.table("chat_messages")
        .select("user_id")
        .eq("role", "assistant")
        .execute()
    ).data or []
    county_volume: dict[str, int] = {}
    for r in asst_rows:
        fips = user_to_county.get(r["user_id"])
        if not fips:
            continue
        county_volume[fips] = county_volume.get(fips, 0) + 1
    county_query_volume = sorted(
        ({"county_fips": k, "county_name": county_by_id.get(k, k), "count": v}
         for k, v in county_volume.items()),
        key=lambda x: x["count"],
        reverse=True,
    )[:20]

    fb_rows = (
        client.table("response_feedback")
        .select("rating")
        .execute()
    ).data or []
    feedback_distribution = {"positive": 0, "negative": 0}
    for r in fb_rows:
        if r["rating"] == 1:
            feedback_distribution["positive"] += 1
        elif r["rating"] == -1:
            feedback_distribution["negative"] += 1

    score_rows = (
        client.table("human_eval_scores")
        .select("accuracy_score, created_at")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    ).data or []
    if score_rows:
        avg_score = sum(r["accuracy_score"] for r in score_rows) / len(score_rows)
    else:
        avg_score = None
    human_eval_summary = {
        "score_count": len(score_rows),
        "mean_accuracy_score": round(avg_score, 2) if avg_score is not None else None,
    }

    user_query_rows = (
        client.table("chat_messages")
        .select("content")
        .eq("role", "user")
        .eq("content_type", "text")
        .limit(2000)
        .execute()
    ).data or []
    freq: dict[str, int] = {}
    for r in user_query_rows:
        key = (r.get("content") or "").strip()
        if not key:
            continue
        freq[key] = freq.get(key, 0) + 1
    top_user_queries = sorted(
        ({"query": q, "count": c} for q, c in freq.items()),
        key=lambda x: x["count"],
        reverse=True,
    )[:20]

    recent_eval_runs = (
        client.table("eval_runs")
        .select("*")
        .order("run_at", desc=True)
        .limit(10)
        .execute()
    ).data or []

    return {
        "totals": totals,
        "language_split": language_split,
        "county_query_volume": county_query_volume,
        "feedback_distribution": feedback_distribution,
        "human_eval_summary": human_eval_summary,
        "top_user_queries": top_user_queries,
        "recent_eval_runs": recent_eval_runs,
    }
