"""Service logic for the spray_feedback table (F4 Phase 6)."""
from services.spray_record import get_record
from services.user import _get_service_client
from utils.db import _assert_insert


def verify_record_ownership(record_id: str, farmer_id: str) -> bool:
    """Confirms the spray record belongs to the given farmer."""
    return get_record(record_id, farmer_id) is not None


def insert_spray_feedback(
    record_id: str, farmer_id: str, rating: int, comment: str | None
) -> dict:
    """Inserts a new feedback row for the specified spray record, stamping the farmer_id."""
    row = {
        "record_id": record_id,
        "farmer_id": farmer_id,
        "rating": rating,
        "comment": comment,
    }
    result = _get_service_client().table("spray_feedback").insert(row).execute()
    _assert_insert(result, f"spray_feedback (farmer {farmer_id}, record {record_id})")
    return result.data[0]
