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
    "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}, {"id": "tavium"}],
    "weather_thresholds": {
        "wind_mph": {"min": 3.0, "max": 10.0},
        "air_temp_f": {"min": 50.0, "max": 91.0},
        "rain_free_hours_required": 48,
    },
}


def _req(product="engenia", at=datetime(2026, 5, 1, 9, 0), **attest):
    return SprayCheckRequest(
        lat=34.7, lon=-91.8, product=product, at=at, attestation=attest
    )


def _weather(wind=6.0, temp=78.0, precip=0.0, risk="low", available=True):
    if not available:
        return {"available": False}
    return {
        "available": True,
        "wind_speed_mph": wind,
        "temp_f": temp,
        "precip_next_48h_in": precip,
        "inversion": {"risk": risk, "is_estimate": True, "reason": "x"},
    }


def _check(gate, check_id):
    return next(c for c in gate.checks if c.id == check_id)


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
    assert {g.gate for g in resp.gates} == {"A", "C"}
    assert resp.weather_available is True
