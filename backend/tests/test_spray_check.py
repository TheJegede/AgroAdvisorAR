import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.spray import SprayCheckRequest  # noqa: E402
from services import spray_check  # noqa: E402

RULES = {
    "rule_version": "2026-AR-OTT",
    "season_window": {"start": "2026-04-15", "end": "2026-06-30"},
    "buffers_ft": {
        "research_station": 5280,
        "organic_specialty": 2640,
        "non_tolerant_crop": 1320,
    },
    "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}, {"id": "tavium"}],
    "weather_thresholds": {
        "wind_mph": {"min": 3.0, "max": 10.0},
        "air_temp_f": {"min": 50.0, "max": 91.0},
        "rain_free_hours_required": 48,
        "downwind_half_angle_deg": 45,
        "soil_moisture_max": 0.45,
    },
}

# A station ~10 mi from the (34.7, -91.8) test field — well outside the 1-mi buffer.
FAR_STATION = {"id": "far", "name": "Far REC", "lat": 34.85, "lon": -91.8}
# A station essentially on top of the test field — inside the 1-mi buffer.
NEAR_STATION = {"id": "near", "name": "Near REC", "lat": 34.701, "lon": -91.8}


def _req(product="engenia", at=datetime(2026, 5, 1, 9, 0), **attest):
    return SprayCheckRequest(
        lat=34.7, lon=-91.8, product=product, at=at, attestation=attest
    )


def _weather(wind=6.0, temp=78.0, precip=0.0, risk="low", available=True, wind_dir=180.0, soil=0.2):
    if not available:
        return {"available": False}
    return {
        "available": True,
        "wind_speed_mph": wind,
        "temp_f": temp,
        "precip_next_48h_in": precip,
        "wind_direction_deg": wind_dir,
        "soil_moisture_0_1cm": soil,
        "inversion": {"risk": risk, "is_estimate": True, "reason": "x", "reason_es": "y"},
    }


def _check(gate, check_id):
    return next(c for c in gate.checks if c.id == check_id)


def test_run_spray_check_evaluated_at_is_utc_aware():
    # Frozen legal record must carry an unambiguous UTC offset, not a naive
    # local-to-the-container timestamp. (F8)
    from datetime import timezone

    resp = spray_check.run_spray_check(_req(), RULES, _weather(), [FAR_STATION])
    assert resp.evaluated_at.tzinfo is not None
    assert resp.evaluated_at.utcoffset() == timezone.utc.utcoffset(None)


# ---- Gate A ----

def test_gate_a_pass_in_season_approved_product():
    gate = spray_check.evaluate_gate_a(RULES, _req())
    assert gate.gate == "A"
    assert gate.status == "pass"


def test_gate_a_fail_out_of_season():
    gate = spray_check.evaluate_gate_a(RULES, _req(at=datetime(2026, 7, 15, 9, 0)))
    assert gate.status == "fail"
    assert _check(gate, "in_season").status == "fail"


def test_gate_a_fail_unapproved_product():
    gate = spray_check.evaluate_gate_a(RULES, _req(product="banvel"))
    assert gate.status == "fail"
    assert _check(gate, "product_approved").status == "fail"


def test_gate_a_fail_after_cutoff():
    gate = spray_check.evaluate_gate_a(RULES, _req(at=datetime(2026, 7, 1, 9, 0)))
    assert _check(gate, "within_cutoff").status == "fail"


# ---- Gate B ----

def test_gate_b_station_buffer_pass_when_field_well_outside():
    gate = spray_check.evaluate_gate_b(RULES, _req(), [FAR_STATION])
    assert gate.gate == "B"
    assert _check(gate, "station_buffer").status == "pass"


def test_gate_b_station_buffer_fail_when_field_inside_ring():
    gate = spray_check.evaluate_gate_b(RULES, _req(), [NEAR_STATION])
    assert _check(gate, "station_buffer").status == "fail"
    assert gate.status == "fail"


def test_gate_b_station_buffer_needs_confirmation_when_no_stations():
    gate = spray_check.evaluate_gate_b(RULES, _req(), [])
    assert _check(gate, "station_buffer").status == "needs_confirmation"


def test_gate_b_neighbor_checks_need_confirmation_unattested():
    gate = spray_check.evaluate_gate_b(RULES, _req(), [FAR_STATION])
    assert _check(gate, "non_tolerant_neighbor").status == "needs_confirmation"
    assert _check(gate, "organic_specialty").status == "needs_confirmation"


def test_gate_b_neighbor_checks_pass_when_attested():
    gate = spray_check.evaluate_gate_b(
        RULES, _req(sensitive_crops_checked=True, organic_specialty_checked=True),
        [FAR_STATION],
    )
    assert _check(gate, "non_tolerant_neighbor").status == "pass"
    assert _check(gate, "organic_specialty").status == "pass"


def test_gate_b_all_pass_when_clear_and_both_attested():
    gate = spray_check.evaluate_gate_b(
        RULES, _req(sensitive_crops_checked=True, organic_specialty_checked=True),
        [FAR_STATION],
    )
    assert gate.status == "pass"


# ---- Gate C ----

def test_gate_c_all_pass_with_low_inversion_and_attestation():
    gate = spray_check.evaluate_gate_c(
        RULES, _weather(risk="low"), _req(no_inversion_observed=True)
    )
    assert gate.gate == "C"
    assert gate.status == "pass"


def test_gate_c_fail_wind_above_max():
    gate = spray_check.evaluate_gate_c(RULES, _weather(wind=12.0), _req())
    assert _check(gate, "wind_in_range").status == "fail"
    assert gate.status == "fail"


def test_gate_c_fail_wind_below_min():
    gate = spray_check.evaluate_gate_c(RULES, _weather(wind=1.0), _req())
    assert _check(gate, "wind_in_range").status == "fail"


def test_gate_c_fail_temp_out_of_range():
    gate = spray_check.evaluate_gate_c(RULES, _weather(temp=100.0), _req())
    assert _check(gate, "temp_in_range").status == "fail"


def test_gate_c_fail_rain_within_48h():
    gate = spray_check.evaluate_gate_c(RULES, _weather(precip=0.3), _req())
    assert _check(gate, "rain_free_48h").status == "fail"


def test_gate_c_inversion_estimate_alone_yields_needs_confirmation_not_pass():
    # low estimate but applicator has NOT attested -> never auto-pass.
    gate = spray_check.evaluate_gate_c(RULES, _weather(risk="low"), _req())
    assert _check(gate, "no_inversion").status == "needs_confirmation"
    assert gate.status == "needs_confirmation"


def test_gate_c_inversion_needs_confirmation_when_estimate_elevated_even_if_attested():
    gate = spray_check.evaluate_gate_c(
        RULES, _weather(risk="elevated"), _req(no_inversion_observed=True)
    )
    assert _check(gate, "no_inversion").status == "needs_confirmation"


def test_gate_c_all_needs_confirmation_when_weather_unavailable():
    gate = spray_check.evaluate_gate_c(RULES, _weather(available=False), _req())
    assert gate.status == "needs_confirmation"
    assert all(c.status == "needs_confirmation" for c in gate.checks)


# ---- roll-up + response ----

def test_runup_status_fail_beats_needs_confirmation_beats_pass():
    # Gate A passes, Gate C fails (wind) -> overall fail.
    resp = spray_check.run_spray_check(_req(), RULES, _weather(wind=12.0))
    assert resp.overall_status == "fail"
    # Gate A passes, Gate C needs_confirmation (inversion unattested) -> overall needs_confirmation.
    resp2 = spray_check.run_spray_check(_req(), RULES, _weather(risk="low"))
    assert resp2.overall_status == "needs_confirmation"


def test_response_stamps_rule_version_from_resolved_record():
    resp = spray_check.run_spray_check(_req(), RULES, _weather())
    assert resp.rule_version == "2026-AR-OTT"
    assert {g.gate for g in resp.gates} == {"A", "B", "C", "D"}
    assert resp.weather_available is True


def test_runup_includes_gate_b_and_rolls_up():
    # Field inside a station ring -> Gate B fail -> overall fail even when A+C pass.
    resp = spray_check.run_spray_check(
        _req(no_inversion_observed=True, sensitive_crops_checked=True,
             organic_specialty_checked=True),
        RULES, _weather(risk="low"), [NEAR_STATION],
    )
    gate_b = next(g for g in resp.gates if g.gate == "B")
    assert gate_b.status == "fail"
    assert resp.overall_status == "fail"


def test_attestation_has_gate_d_fields():
    from models.spray import ApplicatorAttestation
    a = ApplicatorAttestation(
        license_attested=True,
        training_attested=True,
        additives_ok=True,
        ground_application_only=True,
    )
    assert a.license_attested is True
    assert a.training_attested is True
    assert a.additives_ok is True
    assert a.ground_application_only is True


def test_spray_record_model_roundtrips():
    from datetime import datetime as _dt
    from models.spray import SprayRecord
    rec = SprayRecord(
        id="r1", farmer_id="f1", created_at=_dt(2026, 6, 8, 12, 0),
        lat=34.7, lon=-91.8, product="engenia", applied_at=_dt(2026, 6, 8, 9, 0),
        overall_status="needs_confirmation", rule_version="2026-AR-OTT",
        gates=[], attestation={}, weather_json=None,
    )
    assert rec.product == "engenia"


# ---- Gate D ----

# Field at (34.7, -91.8). A station ~0.97 mi due NORTH (inside the 1-mi research buffer).
NORTH_NEAR = {"id": "n", "name": "North REC", "lat": 34.714, "lon": -91.8}
# A station ~0.9 mi due EAST (inside buffer, crosswind when wind blows north).
EAST_NEAR = {"id": "e", "name": "East REC", "lat": 34.7, "lon": -91.7843}


def _att(**kw):
    return _req(**kw)


def test_gate_d_downwind_fail_when_station_in_cone_and_inside_buffer():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [NORTH_NEAR])
    assert gate.gate == "D"
    assert _check(gate, "downwind_clear").status == "fail"


def test_gate_d_downwind_pass_when_station_is_crosswind():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [EAST_NEAR])
    assert _check(gate, "downwind_clear").status == "pass"


def test_gate_d_downwind_pass_when_station_outside_buffer():
    far_north = {"id": "fn", "name": "Far North", "lat": 34.85, "lon": -91.8}
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [far_north])
    assert _check(gate, "downwind_clear").status == "pass"


def test_gate_d_downwind_needs_confirmation_when_wind_unavailable():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(available=False), [NORTH_NEAR])
    assert _check(gate, "downwind_clear").status == "needs_confirmation"


def test_gate_d_equipment_checks_need_confirmation_unattested():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(), [EAST_NEAR])
    for cid in ("boom_height", "droplet_size", "tank_clean", "additives", "ground_application"):
        assert _check(gate, cid).status == "needs_confirmation"


def test_gate_d_equipment_checks_pass_when_attested():
    gate = spray_check.evaluate_gate_d(
        RULES, _req(boom_height_ok=True, droplet_setup_ok=True, tank_clean_ok=True,
                    additives_ok=True, ground_application_only=True),
        _weather(), [EAST_NEAR],
    )
    for cid in ("boom_height", "droplet_size", "tank_clean", "additives", "ground_application"):
        assert _check(gate, cid).status == "pass"


def test_run_spray_check_includes_gate_d():
    resp = spray_check.run_spray_check(_req(), RULES, _weather(), [EAST_NEAR])
    assert {g.gate for g in resp.gates} == {"A", "B", "C", "D"}


# ---- Spanish parity (Phase 5) ----

def _assert_parity(resp):
    for g in resp.gates:
        assert g.title_es, f"gate {g.gate} missing title_es"
        for c in g.checks:
            assert c.label_es, f"{g.gate}/{c.id} missing label_es"
            assert c.reason_es, f"{g.gate}/{c.id} missing reason_es"


def test_spanish_parity_all_pass_branch():
    resp = spray_check.run_spray_check(
        _req(no_inversion_observed=True, sensitive_crops_checked=True,
             organic_specialty_checked=True, boom_height_ok=True, droplet_setup_ok=True,
             tank_clean_ok=True, additives_ok=True, ground_application_only=True),
        RULES, _weather(risk="low"), [FAR_STATION],
    )
    _assert_parity(resp)


def test_spanish_parity_fail_branch():
    resp = spray_check.run_spray_check(
        _req(at=datetime(2026, 7, 15, 9, 0), product="banvel"),
        RULES, _weather(wind=12.0, wind_dir=180.0), [NEAR_STATION],
    )
    _assert_parity(resp)


def test_spanish_parity_weather_unavailable_branch():
    resp = spray_check.run_spray_check(_req(), RULES, _weather(available=False), [])
    _assert_parity(resp)


# ---- Gate C soil saturation (Phase 5) ----

def test_gate_c_soil_pass_when_below_max():
    gate = spray_check.evaluate_gate_c(RULES, _weather(soil=0.2), _req())
    assert _check(gate, "soil_not_saturated").status == "pass"


def test_gate_c_soil_fail_when_saturated():
    gate = spray_check.evaluate_gate_c(RULES, _weather(soil=0.6), _req())
    assert _check(gate, "soil_not_saturated").status == "fail"


def test_gate_c_soil_needs_confirmation_when_missing():
    wx = _weather()
    wx.pop("soil_moisture_0_1cm")
    gate = spray_check.evaluate_gate_c(RULES, wx, _req())
    assert _check(gate, "soil_not_saturated").status == "needs_confirmation"


def test_spanish_strings_differ_from_english():
    # Parity must be authored, not a copy of the EN string.
    resp = spray_check.run_spray_check(_req(), RULES, _weather(), [FAR_STATION])
    a = next(g for g in resp.gates if g.gate == "A")
    season = _check(a, "in_season")
    assert season.reason_es != season.reason
    assert a.title_es != a.title
