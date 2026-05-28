"""Alert rule evaluation + Redis dedup + Supabase insert."""
import json
import logging
from pathlib import Path

from services.cache import _get_client as _get_redis
from services.gdd_calculator import compute_gdd_since_jan1
from services.user import _get_service_client

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 5 * 24 * 60 * 60  # 5 days


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
    ) -> list[str]:
        """Evaluate alert rules for one farmer. Returns list of pest keys that fired."""
        gdd = await compute_gdd_since_jan1(county_fips)
        redis = _get_redis()
        supabase = _get_service_client()
        fired: list[str] = []

        for rule in self._rules:
            if rule["crop"] not in primary_crops:
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
                    logger.warning("Redis exists check failed key=%s", redis_key)

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
                    redis.set(redis_key, "1", ex=DEDUP_TTL_SECONDS)
                except Exception:
                    logger.warning("Redis set failed key=%s", redis_key)

            fired.append(pest)
            logger.info("Alert fired farmer=%s pest=%s gdd=%.1f", farmer_id, pest, gdd)

        return fired
