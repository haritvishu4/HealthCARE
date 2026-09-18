import io
import json
import unicodedata
import wave

import httpx
import pytest
from app.models import Consultation, Document, Patient
from app.security import Actor, authenticate
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas


def intake(client, patient, **kwargs):
    response = client.post(
        "/api/patient/intake", json={"patient": patient, "consent": True, **kwargs}
    )
    assert response.status_code == 200, response.text
    return response.json()


def analyze(client, c):
    response = client.post(
        "/api/ai/analyze",
        json={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
    )
    assert response.status_code == 200, response.text
    c["version"] = response.json()["version"]
    return response.json()


def gemini(report):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(report)}]}}
            ]
        },
    )


def test_complete_flow_and_immutable_pdf(app, client, provider, patient, report):
    seen = []

    def mock(request):
        seen.append(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "test-gemini"
        assert patient["name"] not in request.content.decode()
        return gemini(report)

    provider(mock)
    c = intake(client, patient)
    result = analyze(client, c)
    assert result["physician_approval_required"] is True
    aid = result["analysis_id"]
    generated = client.post(
        "/api/prescription/generate",
        json={
            "consultation_id": c["consultation_id"],
            "analysis_id": aid,
            "expected_version": c["version"],
        },
    )
    assert generated.status_code == 200, generated.text
    url = generated.json()["pdf_url"]
    pdf = client.get(url)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    text = unicodedata.normalize("NFKC", text)
    assert "PHYSICIAN APPROVAL REQUIRED" in text and patient["name"] in text
    assert "Final prescription requires physician approval" in text
    assert "Clinical summary" in text
    assert report["summary"] in text
    assert report["symptoms_analysis"] in text
    reviewed = client.post(
        f"/api/consultation/{c['consultation_id']}/review",
        json={
            "expected_version": c["version"],
            "decision": "accept",
            "doctor_notes": "Reviewed for test only",
            "summary": {},
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    c["version"] = reviewed.json()["version"]
    unchanged = client.patch(
        f"/api/consultation/{c['consultation_id']}/summary",
        json={"expected_version": c["version"], "summary": {}},
    )
    assert unchanged.json()["status"] == "reviewed"
    assert client.get(url).content == pdf.content
    second = intake(
        client, {**patient, "symptoms": "New reported symptom"}, patient_id=c["patient_id"]
    )
    analyze(client, second)
    assert "Previous patient-reported" in json.dumps(seen[-1])
    history = client.get(f"/api/patient/{c['patient_id']}/history").json()
    assert len(history["items"]) == 2
    assert history["items"][1]["prescriptions"][0]["download_url"] == url
    with app.state.db.sessions() as s:
        p = s.get(Patient, c["patient_id"])
        record = s.get(Consultation, c["consultation_id"])
        assert b"Test Patient" not in p.data and b"penicillin" not in record.data


def test_auth_and_cross_patient_isolation(app, client, provider, patient, report):
    assert (
        client.get("/api/patients", headers={"Authorization": "Bearer invalid"}).status_code == 401
    )
    provider(lambda _: gemini(report))
    app.dependency_overrides[authenticate] = lambda: Actor("patient-a", "patient")
    c = intake(client, patient)
    analysis = analyze(client, c)
    pdf = client.post(
        "/api/prescription/generate",
        json={
            "consultation_id": c["consultation_id"],
            "analysis_id": analysis["analysis_id"],
            "expected_version": c["version"],
        },
    ).json()
    assert (
        client.post(
            f"/api/consultation/{c['consultation_id']}/review",
            json={"expected_version": c["version"], "summary": {}, "decision": "accept"},
        ).status_code
        == 403
    )
    app.dependency_overrides[authenticate] = lambda: Actor("patient-b", "patient")
    assert client.get("/api/patients").json()["items"] == []
    for path in (
        f"/api/consultation/{c['consultation_id']}",
        f"/api/patient/{c['patient_id']}/history",
        pdf["pdf_url"],
    ):
        assert client.get(path).status_code == 404
    app.dependency_overrides[authenticate] = lambda: Actor("patient-a", "patient")
    shared = client.post(
        f"/api/consultation/{c['consultation_id']}/share",
        json={"expected_version": c["version"], "doctor_id": "doctor-a"},
    ).json()
    app.dependency_overrides[authenticate] = lambda: Actor("doctor-a", "doctor")
    assert client.get(pdf["pdf_url"]).status_code == 200
    assert len(client.get("/api/consultations").json()["items"]) == 1
    # A shared old visit must not disclose private updates from a later unshared visit.
    app.dependency_overrides[authenticate] = lambda: Actor("patient-a", "patient")
    intake(
        client,
        {**patient, "medical_history": "Private later information"},
        patient_id=c["patient_id"],
    )
    app.dependency_overrides[authenticate] = lambda: Actor("doctor-a", "doctor")
    assert (
        "Private later information"
        not in client.get(f"/api/patient/{c['patient_id']}/history").text
    )
    app.dependency_overrides[authenticate] = lambda: Actor("patient-a", "patient")
    revoke = client.patch(
        f"/api/consultation/{c['consultation_id']}/consent",
        json={"expected_version": shared["version"], "consent": False},
    )
    assert revoke.status_code == 200
    app.dependency_overrides[authenticate] = lambda: Actor("doctor-a", "doctor")
    assert client.get(pdf["pdf_url"]).status_code == 404


def test_validation_stale_writes_and_missing_key(app, client, patient):
    invalid = client.post("/api/patient/intake", json={"patient": {**patient, "age": 999}})
    assert invalid.status_code == 422 and patient["name"] not in invalid.text
    c = intake(client, patient)
    updated = intake(
        client,
        {**patient, "duration": "Three days"},
        patient_id=c["patient_id"],
        consultation_id=c["consultation_id"],
        expected_version=c["version"],
    )
    stale = client.post(
        "/api/patient/intake",
        json={
            "patient": patient,
            "consultation_id": c["consultation_id"],
            "expected_version": c["version"],
        },
    )
    assert stale.status_code == 409
    app.state.settings.gemini_api_key = ""
    response = client.post(
        "/api/ai/analyze",
        json={"consultation_id": c["consultation_id"], "expected_version": updated["version"]},
    )
    assert response.status_code == 503 and "GEMINI_API_KEY" in response.text
    assert client.get(f"/api/consultation/{c['consultation_id']}").json()["ai_analysis"] is None


def test_unavailable_gemini_model_preserves_intake_and_can_retry(
    app, client, provider, patient, report
):
    attempts = []

    def mock(request):
        attempts.append(request.url.path)
        if request.url.path.endswith("/gemini-2.5-flash:generateContent"):
            return httpx.Response(
                404,
                json={"error": {"message": "Private upstream details", "status": "NOT_FOUND"}},
            )
        assert request.url.path.endswith("/gemini-3.5-flash:generateContent")
        return gemini(report)

    provider(mock)
    app.state.settings.gemini_model = "gemini-2.5-flash"
    c = intake(client, patient)
    response = client.post(
        "/api/ai/analyze",
        json={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
    )
    assert response.status_code == 503
    assert "GEMINI_MODEL" in response.json()["detail"]
    assert "restart" in response.json()["detail"]
    assert "Private upstream details" not in response.text
    saved = client.get(f"/api/consultation/{c['consultation_id']}").json()
    assert saved["ai_analysis"] is None
    assert saved["patient"]["symptoms"] == patient["symptoms"]
    assert saved["version"] == c["version"]
    assert len(attempts) == 1  # Do not silently switch models or fabricate a draft.

    app.state.settings.gemini_model = "gemini-3.5-flash"
    result = analyze(client, c)
    generated = client.post(
        "/api/prescription/generate",
        json={
            "consultation_id": c["consultation_id"],
            "analysis_id": result["analysis_id"],
            "expected_version": c["version"],
        },
    )
    assert generated.status_code == 200, generated.text
    pdf = client.get(generated.json()["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert report["summary"] in text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"candidates": [{"finishReason": "MAX_TOKENS"}]},
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": '{"diagnosis":"invented"}'}]},
                }
            ]
        },
    ],
)
def test_invalid_ai_never_saved(client, provider, patient, payload):
    provider(lambda _: httpx.Response(200, json=payload))
    c = intake(client, patient)
    response = client.post(
        "/api/ai/analyze",
        json={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
    )
    assert response.status_code == 502
    assert client.get(f"/api/consultation/{c['consultation_id']}").json()["ai_analysis"] is None


def test_consent_required_before_provider(app, client, provider, patient):
    def forbidden(_):
        raise AssertionError("Provider must not be called without consent")

    provider(forbidden)
    c = client.post("/api/patient/intake", json={"patient": patient, "consent": False}).json()
    response = client.post(
        "/api/ai/analyze",
        json={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
    )
    assert response.status_code == 403


def test_sarvam_audio_contract(client, provider, patient):
    def mock(request):
        assert request.url.host == "api.sarvam.ai"
        assert request.headers["api-subscription-key"] == "test-sarvam"
        assert b"saaras:v3" in request.content and b"hi-IN" in request.content
        return httpx.Response(200, json={"transcript": "मुझे बुखार है", "language_code": "hi-IN"})

    provider(mock)
    c = intake(client, patient)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)
    response = client.post(
        "/api/audio/transcribe",
        data={
            "consultation_id": c["consultation_id"],
            "expected_version": c["version"],
            "language": "hi-IN",
        },
        files={"file": ("speech.wav", buffer.getvalue(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "मुझे बुखार है"
    saved = client.get(f"/api/consultation/{c['consultation_id']}").json()
    assert saved["transcripts"][0]["text"] == "मुझे बुखार है"


def test_document_upload_native_pdf_and_encrypted_download(app, client, patient):
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(
        40, 700, "Laboratory report: fictional patient sample data for OCR verification."
    )
    canvas.save()
    c = intake(client, patient)
    response = client.post(
        "/api/document/upload",
        data={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
        files={"file": ("../../test.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["provider"] == "pdf_text" and doc["confidence"] is None
    assert doc["name"] == "test.pdf" and "Laboratory" in doc["extracted_text"]
    assert client.get(f"/api/document/{doc['id']}/download").content == buffer.getvalue()
    with app.state.db.sessions() as s:
        assert not s.get(Document, doc["id"]).file_bytes.startswith(b"%PDF")
    deleted = client.delete(f"/api/document/{doc['id']}?expected_version={doc['version']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/document/{doc['id']}/download").status_code == 404


def test_scanned_image_ocr_contract(client, provider, patient):
    from PIL import Image

    def mock(request):
        assert request.url.host == "api.ocr.space" and request.headers["apikey"] == "test-ocr"
        return httpx.Response(
            200,
            json={
                "IsErroredOnProcessing": False,
                "ParsedResults": [
                    {"FileParseExitCode": 1, "ParsedText": "Laboratory test fixture text"}
                ],
            },
        )

    provider(mock)
    c = intake(client, patient)
    image = io.BytesIO()
    Image.new("RGB", (80, 80), "white").save(image, "PNG")
    response = client.post(
        "/api/document/upload",
        data={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
        files={"file": ("scan.png", image.getvalue(), "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "ocrspace"


def test_file_limits_and_spoofed_uploads(app, client, patient):
    c = intake(client, patient)
    response = client.post(
        "/api/document/upload",
        data={"consultation_id": c["consultation_id"], "expected_version": c["version"]},
        files={"file": ("fake.pdf", b"<script>bad</script>", "application/pdf")},
    )
    assert response.status_code == 415
    response = client.post(
        "/api/patient/intake",
        content=b"0" * (app.state.settings.max_upload_bytes + 1024 * 1024 + 1),
    )
    assert response.status_code == 413


def test_openapi_and_cors(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/patient/intake"]["post"]["security"] == [{"HTTPBearer": []}]
    response = client.options(
        "/api/patient/intake",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.get("/api/system", headers={"Origin": "https://untrusted.invalid"})
    assert "access-control-allow-origin" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_rate_limiting(client):
    for _ in range(60):
        assert client.get("/api/system").status_code == 200
    assert client.get("/api/system").status_code == 429
