import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


REPORT_FIXTURE = {
    "id": "aaaabbbb-1234-5678-abcd-111122223333",
    "incident_date": "2024-07-14",
    "county_fips": "05055",
    "affected_crop": "soybean",
    "affected_acres": 50.0,
    "suspected_herbicide": "dicamba",
    "symptoms_description": "Cupping and strapping observed on leaves",
    "neighboring_applicator": "John Doe Farm",
    "weather_json": {
        "available": True,
        "hourly_summary": {
            "wind_speed_mph_avg": 8.2,
            "wind_direction_label": "S",
            "temp_f_at_noon": 91.4,
        },
    },
}

PROFILE_FIXTURE = {
    "full_name": "Test Farmer",
    "email": "testfarmer@example.com",
    "county_fips": "05055",
}


def test_generate_complaint_pdf_returns_valid_pdf_bytes():
    pdf_mod = importlib.import_module("services.pdf_generator")
    pdf_bytes = pdf_mod.generate_complaint_pdf(REPORT_FIXTURE, PROFILE_FIXTURE)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_complaint_pdf_handles_missing_weather():
    pdf_mod = importlib.import_module("services.pdf_generator")
    report = {**REPORT_FIXTURE, "weather_json": None}
    pdf_bytes = pdf_mod.generate_complaint_pdf(report, {})

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_complaint_pdf_handles_empty_profile():
    pdf_mod = importlib.import_module("services.pdf_generator")
    pdf_bytes = pdf_mod.generate_complaint_pdf(REPORT_FIXTURE, {})

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_spray_record_pdf_returns_pdf_bytes():
    from services.pdf_generator import generate_spray_record_pdf, SPRAY_DISCLAIMER
    record = {
        "id": "rec-1", "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "needs_confirmation",
        "rule_version": "2026-AR-OTT",
        "gates": [
            {"gate": "A", "title": "Legal window", "status": "pass", "checks": [
                {"id": "in_season", "label": "Inside the dicamba season window",
                 "tier": "verifiable_fact", "status": "pass", "reason": "ok", "observed": "2026-06-08"}
            ]},
        ],
        "attestation": {"no_inversion_observed": True, "boom_height_ok": True},
        "weather_json": {"available": True, "wind_speed_mph": 6.0, "temp_f": 78.0},
    }
    out = generate_spray_record_pdf(record, {"full_name": "Jane Farmer", "email": "j@x.com"})
    assert out[:4] == b"%PDF"
    assert "solely responsible for verifying" in SPRAY_DISCLAIMER


def test_generate_spray_record_pdf_handles_missing_weather_and_empty_profile():
    from services.pdf_generator import generate_spray_record_pdf
    record = {
        "id": "rec-2", "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "fail",
        "rule_version": "2026-AR-OTT", "gates": [], "attestation": {}, "weather_json": None,
    }
    out = generate_spray_record_pdf(record, {})
    assert out[:4] == b"%PDF"
