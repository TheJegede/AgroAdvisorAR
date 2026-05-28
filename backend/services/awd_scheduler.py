"""AWD irrigation stage calculator — per field, per drainage class."""
import json
import math
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

_THRESHOLDS_PATH = Path(__file__).parent.parent / "data" / "awd_thresholds.json"
_thresholds: dict | None = None


class AWDStageResult(BaseModel):
    field_name: str
    days_to_threshold: int
    recommendation: Literal["maintain flood", "prepare to re-flood", "re-flood now"]
    aquifer_stress_level: Literal["normal", "stressed", "critical"]
    well_depth_m: Optional[float] = None


def _get_thresholds() -> dict:
    global _thresholds
    if _thresholds is None:
        _thresholds = json.loads(_THRESHOLDS_PATH.read_text())
    return _thresholds


def compute_awd_stage(
    field_name: str,
    last_flood_date: date,
    drainage_class: str,
    current_well_m: float | None,
    aquifer_stress_level: Literal["normal", "stressed", "critical"] = "normal",
) -> AWDStageResult:
    thresholds = _get_thresholds()
    key = (drainage_class or "").lower()
    cfg = thresholds.get(key) or thresholds["default"]
    dry_rate: float = cfg["dry_rate_cm_per_day"]
    threshold_cm: float = cfg["threshold_cm"]

    days_elapsed = max(0, (date.today() - last_flood_date).days)
    estimated_depth_cm = days_elapsed * dry_rate

    if estimated_depth_cm >= threshold_cm:
        days_left = 0
    else:
        days_left = math.ceil((threshold_cm - estimated_depth_cm) / dry_rate)

    if days_left <= 0:
        rec: Literal["maintain flood", "prepare to re-flood", "re-flood now"] = "re-flood now"
    elif days_left <= 2:
        rec = "prepare to re-flood"
    else:
        rec = "maintain flood"

    return AWDStageResult(
        field_name=field_name,
        days_to_threshold=days_left,
        recommendation=rec,
        aquifer_stress_level=aquifer_stress_level,
        well_depth_m=current_well_m,
    )


def format_awd_context(results: list[AWDStageResult]) -> str:
    lines = ["[AWD IRRIGATION STATUS]"]
    for r in results:
        well_str = f" USGS well depth: {r.well_depth_m:.2f}m." if r.well_depth_m is not None else ""
        lines.append(
            f"Field '{r.field_name}': {r.recommendation}. "
            f"Days to re-flood threshold: {r.days_to_threshold}. "
            f"Aquifer stress: {r.aquifer_stress_level}.{well_str}"
        )
    return "\n".join(lines)
