from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(max_length=8000)]
Short = Annotated[str, Field(max_length=500)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatientDetails(Strict):
    name: str = Field(min_length=1, max_length=200)
    age: int = Field(ge=0, le=120)
    gender: Literal["Male", "Female", "Other", "Prefer not to say"]
    contact: Short = ""
    symptoms: Text = ""
    duration: Short = ""
    medical_history: Text = ""
    allergies: Text = ""
    current_medicines: Text = ""
    additional_details: dict[Short, Text] = Field(default_factory=dict, max_length=20)
    mode: Literal["General", "AYUSH"] = "General"


class IntakeRequest(Strict):
    patient: PatientDetails
    patient_id: str | None = None
    consultation_id: str | None = None
    expected_version: int | None = None
    consent: bool = False


class AnalyzeRequest(Strict):
    consultation_id: str
    expected_version: int
    # Optional additional evidence, stored alongside the existing consultation input.
    transcript: Text = ""
    ocr_text: Text = ""


class ClinicalReport(Strict):
    summary: Text
    symptoms_analysis: Text
    possible_conditions: list[Short] = Field(max_length=10)
    severity: Literal[
        "urgent_review", "prompt_review", "routine_review", "insufficient_information"
    ]
    recommended_tests: list[Short] = Field(max_length=20)
    precautions: list[Short] = Field(max_length=20)
    doctor_notes: Text
    missing_details: list[Short] = Field(default_factory=list, max_length=20)
    follow_up_questions: list[Short] = Field(default_factory=list, max_length=10)
    physician_approval_required: Literal[True] = True


class PDFRequest(Strict):
    consultation_id: str
    analysis_id: str
    expected_version: int


class SummaryRequest(Strict):
    expected_version: int
    summary: dict[Short, Text] = Field(max_length=30)


class ReviewRequest(SummaryRequest):
    decision: Literal["accept", "reject"]
    doctor_notes: Text = ""


class ShareRequest(Strict):
    expected_version: int
    doctor_id: str | None = Field(default=None, max_length=128)


class ConsentRequest(Strict):
    expected_version: int
    consent: bool
