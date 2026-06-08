"""Dicamba gate-evaluation engine (F4 Phase 1: Gates A + C).

Core principle (PRD §3/§4): never invent certainty. Verifiable facts are stated
as pass/fail; items the tool cannot measure (the inversion estimate) return
needs_confirmation and can only reach 'pass' on an explicit applicator
attestation — never automatically. Gates B + D append in later phases with no
signature change.
"""
from datetime import datetime

from models.spray import CheckResult, GateResult, SprayCheckRequest, SprayCheckResponse
from services import spray_rules


def _rollup(statuses: list[str]) -> str:
    """fail if any failed; else needs_confirmation if any needs it; else pass."""
    if "fail" in statuses:
        return "fail"
    if "needs_confirmation" in statuses:
        return "needs_confirmation"
    return "pass"


def _gate(gate_id: str, title: str, checks: list[CheckResult]) -> GateResult:
    return GateResult(
        gate=gate_id,
        title=title,
        status=_rollup([c.status for c in checks]),
        checks=checks,
    )


def evaluate_gate_a(rules: dict, req: SprayCheckRequest) -> GateResult:
    """Gate A — Legal window. Pure rules lookup; all checks verifiable_fact."""
    on_date = req.at.date()
    window = rules["season_window"]

    in_season = spray_rules.in_season(rules, on_date)
    season_check = CheckResult(
        id="in_season",
        label="Inside the dicamba season window",
        tier="verifiable_fact",
        status="pass" if in_season else "fail",
        reason=(
            "Application date is inside the season window."
            if in_season
            else "Application date is outside the season window."
        ),
        observed=on_date.isoformat(),
        expected=f"{window['start']} to {window['end']}",
    )

    approved = req.product in spray_rules.approved_product_ids(rules)
    product_check = CheckResult(
        id="product_approved",
        label="Product is an approved over-the-top dicamba",
        tier="verifiable_fact",
        status="pass" if approved else "fail",
        reason=(
            f"'{req.product}' is an approved over-the-top product."
            if approved
            else f"'{req.product}' is not on the approved over-the-top product list."
        ),
        observed=req.product,
        expected=", ".join(sorted(spray_rules.approved_product_ids(rules))),
    )

    within_cutoff = on_date.isoformat() <= window["end"]
    cutoff_check = CheckResult(
        id="within_cutoff",
        label="On or before the season cutoff date",
        tier="verifiable_fact",
        status="pass" if within_cutoff else "fail",
        reason=(
            "Application date is on or before the cutoff."
            if within_cutoff
            else "Application date is past the season cutoff."
        ),
        observed=on_date.isoformat(),
        expected=f"on or before {window['end']}",
    )

    return _gate("A", "Legal window", [season_check, product_check, cutoff_check])


def evaluate_gate_c(rules: dict, weather: dict, req: SprayCheckRequest) -> GateResult:
    """Gate C — Weather now. Verifiable thresholds + the human-attested inversion."""
    available = weather.get("available", False)
    lo_w, hi_w = spray_rules.wind_bounds(rules)
    lo_t, hi_t = spray_rules.temp_bounds(rules)
    rain_hours = spray_rules.rain_free_hours_required(rules)

    def verifiable(check_id, label, value, ok, reason_ok, reason_bad, expected):
        # When weather is unavailable, a verifiable fact cannot be measured ->
        # needs_confirmation, never a guessed pass/fail.
        if not available or value is None:
            return CheckResult(
                id=check_id, label=label, tier="verifiable_fact",
                status="needs_confirmation",
                reason="Live weather unavailable — confirm this on the ground.",
                observed=None, expected=expected,
            )
        return CheckResult(
            id=check_id, label=label, tier="verifiable_fact",
            status="pass" if ok else "fail",
            reason=reason_ok if ok else reason_bad,
            observed=str(value), expected=expected,
        )

    wind = weather.get("wind_speed_mph")
    wind_check = verifiable(
        "wind_in_range", "Wind speed within the allowed range", wind,
        wind is not None and lo_w <= wind <= hi_w,
        f"Wind {wind} mph is within range.", f"Wind {wind} mph is outside range.",
        f"{lo_w}-{hi_w} mph",
    )

    temp = weather.get("temp_f")
    temp_check = verifiable(
        "temp_in_range", "Air temperature within the allowed range", temp,
        temp is not None and lo_t <= temp <= hi_t,
        f"Temp {temp}°F is within range.", f"Temp {temp}°F is outside range.",
        f"{lo_t}-{hi_t} °F",
    )

    precip = weather.get("precip_next_48h_in")
    rain_check = verifiable(
        "rain_free_48h", f"No rain forecast within {rain_hours} hours", precip,
        precip is not None and precip == 0,
        "No rain forecast in the window.",
        f"{precip} in of rain forecast in the window.",
        "0 in",
    )

    # Inversion — ALWAYS human-attested. Only 'pass' when the estimate is low AND
    # the applicator explicitly confirms no inversion; otherwise needs_confirmation.
    inversion = weather.get("inversion") or {}
    risk = inversion.get("risk", "unknown")
    attested = req.attestation.no_inversion_observed is True
    if available and risk == "low" and attested:
        inv_status = "pass"
        inv_reason = "Estimate is low risk and applicator confirmed no inversion."
    else:
        inv_status = "needs_confirmation"
        inv_reason = inversion.get("reason") or (
            "Inversion cannot be measured — applicator must confirm no inversion."
        )
    inversion_check = CheckResult(
        id="no_inversion",
        label="No temperature inversion",
        tier="human_attested",
        status=inv_status,
        reason=inv_reason,
        observed=f"risk={risk} (estimate)",
        expected="applicator-confirmed no inversion",
    )

    return _gate(
        "C", "Weather now",
        [wind_check, temp_check, rain_check, inversion_check],
    )


def run_spray_check(req: SprayCheckRequest, rules: dict, weather: dict) -> SprayCheckResponse:
    """Assemble Gate A + C, roll up overall status, stamp the rule version."""
    gates = [evaluate_gate_a(rules, req), evaluate_gate_c(rules, weather, req)]
    return SprayCheckResponse(
        overall_status=_rollup([g.status for g in gates]),
        rule_version=rules["rule_version"],
        evaluated_at=datetime.now(),
        weather_available=weather.get("available", False),
        gates=gates,
    )
