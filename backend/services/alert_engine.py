"""Alert rule evaluation + Redis dedup + Supabase insert."""
import json
import logging
from datetime import date
from pathlib import Path

from services.cache import _get_client as _get_redis
from services.gdd_calculator import compute_gdd_since_jan1
from services.user import _get_service_client
from utils.crops import canonical_crop

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 5 * 24 * 60 * 60  # 5 days (default floor)
_DAY_SECONDS = 24 * 60 * 60


def _dedup_ttl_for(rule: dict) -> int:
    """Dedup TTL must be ≥ the rule's validity window, or the identical alert
    re-fires mid-window. A flood-window rule stays satisfied for
    requires_recent_flood_days days; cap the TTL to at least that long."""
    flood_days = rule.get("requires_recent_flood_days")
    if flood_days:
        return max(DEDUP_TTL_SECONDS, int(flood_days) * _DAY_SECONDS)
    return DEDUP_TTL_SECONDS


def _has_recent_flood(rice_fields: list[dict], window_days: int) -> bool:
    today = date.today()
    for field in rice_fields:
        raw_date = field.get("last_flood_date")
        if not raw_date:
            continue
        try:
            flood_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            continue
        days_since_flood = (today - flood_date).days
        if 0 <= days_since_flood <= window_days:
            return True
    return False


class AlertEngine:
    def __init__(self, rules_path: str | None = None):
        if rules_path is None:
            rules_path = str(Path(__file__).parent.parent / "data" / "alert_rules.json")
        with open(rules_path) as f:
            self._rules = json.load(f)

    async def run_for_farmer(
        self,
        farmer_id: str,
        county_fips: str,
        primary_crops: list[str],
        language: str,
        rice_fields: list[dict] | None = None,
    ) -> list[str]:
        """Evaluate alert rules for one farmer. Returns list of pest keys that fired."""
        gdd = await compute_gdd_since_jan1(county_fips)
        redis = _get_redis()
        supabase = _get_service_client()
        fired: list[str] = []
        crop_set = {canonical_crop(c) for c in primary_crops}
        rice_fields = rice_fields or []

        for rule in self._rules:
            if canonical_crop(rule["crop"]) not in crop_set:
                continue

            recent_flood_days = rule.get("requires_recent_flood_days")
            if recent_flood_days is not None and not _has_recent_flood(
                rice_fields, int(recent_flood_days)
            ):
                continue

            lower: float = rule["gdd_lower"]
            upper: float | None = rule.get("gdd_upper")

            if gdd < lower:
                continue
            if upper is not None and gdd > upper:
                continue

            pest: str = rule["pest"]
            redis_key = f"alert:{farmer_id}:{pest}"

            if redis is not None:
                try:
                    if redis.exists(redis_key):
                        continue
                except Exception:
                    # Dedup state unknown — skip rather than risk a duplicate
                    # insert on every scheduler run during a Redis outage.
                    logger.warning("Redis exists check failed key=%s — skipping", redis_key)
                    continue

            row = {
                "farmer_id": farmer_id,
                "pest": pest,
                "county_fips": county_fips,
                "gdd_value": gdd,
                "message_en": rule["message_en"],
                "message_es": rule["message_es"],
            }

            try:
                supabase.table("alerts").insert(row).execute()
            except Exception:
                logger.exception("Alert insert failed farmer=%s pest=%s", farmer_id, pest)
                continue

            if redis is not None:
                try:
                    redis.set(redis_key, "1", ex=_dedup_ttl_for(rule))
                except Exception:
                    logger.warning("Redis set failed key=%s", redis_key)

            fired.append(pest)
            logger.info("Alert fired farmer=%s pest=%s gdd=%.1f", farmer_id, pest, gdd)

        return fired
