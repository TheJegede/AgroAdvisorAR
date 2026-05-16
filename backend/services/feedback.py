"""Feedback CRUD + rate-limit. Service-role client bypasses RLS — always
filter by user_id manually to prevent cross-user data leaks."""
from services.user import _get_service_client
from services.cache import rate_limit_hit

# Rate limit: 10 feedback submissions per user per hour. Allows re-rating
# (history is append-only) while preventing spam.
FEEDBACK_LIMIT_PER_HOUR = 10
FEEDBACK_WINDOW_SECONDS = 3600


def check_rate_limit(user_id: str) -> tuple[bool, int]:
    """Returns (allowed, remaining). Fails open if Redis is down."""
    key = f"feedback_throttle:{user_id}"
    return rate_limit_hit(key, FEEDBACK_LIMIT_PER_HOUR, FEEDBACK_WINDOW_SECONDS)


def verify_message_ownership(message_id: str, user_id: str) -> bool:
    """Confirm the message exists and belongs to this user. Service-role
    client bypasses RLS, so we filter manually."""
    result = (
        _get_service_client()
        .table("chat_messages")
        .select("id")
        .eq("id", message_id)
        .eq("user_id", user_id)
        .eq("role", "assistant")
        .maybe_single()
        .execute()
    )
    return result.data is not None


def insert_feedback(
    message_id: str,
    user_id: str,
    rating: int,
    comment: str | None,
) -> dict:
    result = (
        _get_service_client()
        .table("response_feedback")
        .insert({
            "message_id": message_id,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
        })
        .execute()
    )
    if not result.data:
        raise RuntimeError(f"Feedback insert returned no data for message {message_id}")
    return result.data[0]
