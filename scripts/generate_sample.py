"""Generate a clearly fictional PDF fixture, without calling any AI service."""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
report = {
    "summary": "Fictional patient-reported intake for demonstrating this software.",
    "symptoms_analysis": "No clinical conclusions are established by this sample.",
    "possible_conditions": [],
    "severity": "insufficient_information",
    "recommended_tests": [],
    "precautions": ["Obtain guidance from the reviewing clinician."],
    "doctor_notes": "Fictional sample. This report is a mocked fixture, not a response from a live medical consultation. Physician approval is required.",
    "missing_details": ["Complete history and clinical observations"],
    "follow_up_questions": ["What additional information would you like to share?"],
}
snapshot = {
    "patient_id": "00000000-0000-4000-8000-000000000001",
    "id": "00000000-0000-4000-8000-000000000002",
    "created_at": datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc).timestamp(),
    "patient": {
        "name": "राहुल शर्मा (fictional sample)",
        "age": 32,
        "gender": "Male",
        "symptoms": "Patient reports feeling unwell. मुझे बुखार है।",
        "duration": "Patient reports two days",
        "medical_history": "Not yet confirmed",
        "allergies": "Not confirmed",
        "current_medicines": "Not confirmed",
        "additional_details": {"drug_and_allergy_history": "Must be verified with the patient."},
    },
    "report": report,
    "human_summary": {},
}


def main():
    from app.services.pdf_service import generate_prescription_pdf

    output = ROOT / "docs" / "sample-draft.pdf"
    output.write_bytes(generate_prescription_pdf(snapshot))
    print("Created docs/sample-draft.pdf using fictional fixture data.")


if __name__ == "__main__":
    main()
