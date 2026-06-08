"""Dicamba gate-evaluation engine (F4 Phase 1: Gates A + C).

Core principle (PRD §3/§4): never invent certainty. Verifiable facts are stated
as pass/fail; items the tool cannot measure (the inversion estimate) return
needs_confirmation and can only reach 'pass' on an explicit applicator
attestation — never automatically. Gates B + D append in later phases with no
signature change.
"""
from datetime import datetime

from models.spray import CheckResult, GateResult, SprayCheckRequest, SprayCheckResponse
from services import spray_rules, spray_stations

_FULL_CIRCLE = 360.0


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


def evaluate_gate_b(
    rules: dict, req: SprayCheckRequest, stations: list[dict]
) -> GateResult:
    """Gate B — Field & buffers. Verifiable station distance + human-attested neighbors.

    Never guesses a pass: an empty station list yields needs_confirmation, and the
    two neighbor checks can only reach 'pass' on an explicit applicator attestation.
    """
    buffers = spray_rules.buffers_ft(rules)
    station_buf = float(buffers["research_station"])

    station, dist_ft = spray_stations.nearest_station(req.lat, req.lon, stations)
    if station is None:
        station_check = CheckResult(
            id="station_buffer",
            label="Clear of research-station buffer",
            tier="verifiable_fact",
            status="needs_confirmation",
            reason="Station data unavailable — confirm distance to any research station on the ground.",
            observed=None,
            expected=f"≥ {station_buf / 5280:.1f} mi ({station_buf:.0f} ft) from research stations",
        )
    else:
        clear = dist_ft >= station_buf
        station_check = CheckResult(
            id="station_buffer",
            label="Clear of research-station buffer",
            tier="verifiable_fact",
            status="pass" if clear else "fail",
            reason=(
                f"Field is outside the research-station buffer ({station['name']})."
                if clear
                else f"Field is inside the research-station buffer for {station['name']}."
            ),
            observed=f"{dist_ft / 5280:.1f} mi to {station['name']}",
            expected=f"≥ {station_buf / 5280:.1f} mi ({station_buf:.0f} ft) from research stations",
        )

    nt_attested = req.attestation.sensitive_crops_checked is True
    nt_buf = float(buffers["non_tolerant_crop"])
    non_tolerant_check = CheckResult(
        id="non_tolerant_neighbor",
        label="Checked for non-dicamba-tolerant crops in the buffer",
        tier="human_attested",
        status="pass" if nt_attested else "needs_confirmation",
        reason=(
            "Applicator confirmed no non-tolerant crops within the buffer."
            if nt_attested
            else f"Confirm no non-dicamba-tolerant crops within {nt_buf / 5280:.2f} mi ({nt_buf:.0f} ft)."
        ),
        observed=None,
        expected=f"no non-tolerant crops within {nt_buf / 5280:.2f} mi ({nt_buf:.0f} ft)",
    )

    org_attested = req.attestation.organic_specialty_checked is True
    org_buf = float(buffers["organic_specialty"])
    organic_check = CheckResult(
        id="organic_specialty",
        label="Checked for organic / specialty crops in the buffer",
        tier="human_attested",
        status="pass" if org_attested else "needs_confirmation",
        reason=(
            "Applicator confirmed no organic or specialty crops within the buffer. "
            "Registry data is incomplete — voluntary FieldWatch registries are not yet integrated."
            if org_attested
            else f"Confirm no organic/specialty crops within {org_buf / 5280:.1f} mi ({org_buf:.0f} ft). "
            "Registry data is incomplete — voluntary FieldWatch registries are not yet integrated."
        ),
        observed=None,
        expected=f"no organic/specialty crops within {org_buf / 5280:.1f} mi ({org_buf:.0f} ft)",
    )

    return _gate(
        "B", "Field & buffers",
        [station_check, non_tolerant_check, organic_check],
    )


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


def _attested_check(check_id, label, ok, attested_reason, unattested_reason):
    """Human-attested Gate D item: pass only on an explicit True attestation."""
    attested = ok is True
    return CheckResult(
        id=check_id, label=label, tier="human_attested",
        status="pass" if attested else "needs_confirmation",
        reason=attested_reason if attested else unattested_reason,
        observed=None, expected="applicator-confirmed",
    )


def evaluate_gate_d(
    rules: dict, req: SprayCheckRequest, weather: dict, stations: list[dict]
) -> GateResult:
    """Gate D — Equipment & target. Verifiable downwind geometry + human-attested setup."""
    half_angle = spray_rules.downwind_half_angle_deg(rules)
    research_buf = float(spray_rules.buffers_ft(rules)["research_station"])
    available = weather.get("available", False)
    wind_dir = weather.get("wind_direction_deg")
    cone_label = f"no research station within a {2 * half_angle:.0f}° downwind cone inside its buffer"

    if not available or wind_dir is None:
        downwind = CheckResult(
            id="downwind_clear", label="No sensitive site downwind of the field",
            tier="verifiable_fact", status="needs_confirmation",
            reason="Wind direction unavailable — confirm downwind exposure on the ground.",
            observed=None, expected=cone_label,
        )
    else:
        wind_toward = (wind_dir + 180.0) % _FULL_CIRCLE
        hit = None
        for s in stations:
            dist = spray_stations.haversine_ft(req.lat, req.lon, s["lat"], s["lon"])
            if dist >= research_buf:
                continue
            bearing = spray_stations.bearing_deg(req.lat, req.lon, s["lat"], s["lon"])
            if spray_stations.angular_diff(wind_toward, bearing) <= half_angle:
                hit = (s, dist, bearing)
                break
        if hit:
            s, dist, bearing = hit
            downwind = CheckResult(
                id="downwind_clear", label="No sensitive site downwind of the field",
                tier="verifiable_fact", status="fail",
                reason=f"{s['name']} is downwind of the field and inside the research-station buffer.",
                observed=f"wind toward {wind_toward:.0f}°; {s['name']} at bearing {bearing:.0f}°, {dist / 5280:.1f} mi",
                expected=cone_label,
            )
        else:
            downwind = CheckResult(
                id="downwind_clear", label="No sensitive site downwind of the field",
                tier="verifiable_fact", status="pass",
                reason="No research station is downwind of the field within its buffer.",
                observed=f"wind toward {wind_toward:.0f}°", expected=cone_label,
            )

    att = req.attestation
    boom = _attested_check(
        "boom_height", "Boom height at or below the label maximum", att.boom_height_ok,
        "Applicator confirmed boom height is within the label maximum.",
        "Confirm the boom is at or below the label maximum height (≤ 2 ft).",
    )
    droplet = _attested_check(
        "droplet_size", "Droplet size Ultra Coarse or coarser", att.droplet_setup_ok,
        "Applicator confirmed nozzles produce Ultra Coarse or coarser droplets.",
        "Confirm nozzle setup produces Ultra Coarse or coarser droplets (per label).",
    )
    tank = _attested_check(
        "tank_clean", "Sprayer cleaned out before loading", att.tank_clean_ok,
        "Applicator confirmed the sprayer was cleaned out.",
        "Confirm the sprayer was cleaned out before loading.",
    )
    additives = _attested_check(
        "additives", "Required additives present, prohibited absent", att.additives_ok,
        "Applicator confirmed approved VRA + DRA are in the tank and AMS is not.",
        "Confirm an approved VRA and DRA are in the tank and that AMS is not added.",
    )
    ground = _attested_check(
        "ground_application", "Ground application only (no aerial)", att.ground_application_only,
        "Applicator confirmed this is a ground application.",
        "Confirm this is a ground application — aerial over-the-top dicamba is prohibited.",
    )

    return _gate("D", "Equipment & target", [downwind, boom, droplet, tank, additives, ground])


def run_spray_check(
    req: SprayCheckRequest, rules: dict, weather: dict, stations: list[dict] | None = None
) -> SprayCheckResponse:
    """Assemble Gates A + B + C + D, roll up overall status, stamp the rule version."""
    gates = [
        evaluate_gate_a(rules, req),
        evaluate_gate_b(rules, req, stations or []),
        evaluate_gate_c(rules, weather, req),
        evaluate_gate_d(rules, req, weather, stations or []),
    ]
    return SprayCheckResponse(
        overall_status=_rollup([g.status for g in gates]),
        rule_version=rules["rule_version"],
        evaluated_at=datetime.now(),
        weather_available=weather.get("available", False),
        gates=gates,
    )
