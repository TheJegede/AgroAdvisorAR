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
