import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.models import Base
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/test.db",
        field_encryption_key=Fernet.generate_key().decode(),
        dev_auth_token="test-token-" + "x" * 40,
        gemini_api_key="test-gemini",
        sarvam_api_key="test-sarvam",
        ocr_api_key="test-ocr",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.db.engine)
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + app.state.settings.dev_auth_token
        yield client


@pytest.fixture
def provider(app, client):
    clients = []

    def install(handler):
        client.portal.call(app.state.client.aclose)
        mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app.state.client = mock
        clients.append(mock)

    return install


@pytest.fixture
def patient():
    return {
        "name": "Test Patient",
        "age": 32,
        "gender": "Female",
        "symptoms": "Patient reports feeling unwell.",
        "duration": "Two days",
        "medical_history": "Patient reported past condition.",
        "allergies": "Patient reports a penicillin allergy",
        "current_medicines": "Not confirmed",
    }


@pytest.fixture
def report():
    return {
        "summary": "Fictional patient reports feeling unwell for two days.",
        "symptoms_analysis": "This test response does not establish a diagnosis.",
        "possible_conditions": ["Cause requires clinical assessment"],
        "severity": "insufficient_information",
        "recommended_tests": [],
        "precautions": ["Ask the reviewing clinician for guidance."],
        "doctor_notes": "Fictional mocked test data; verify all information.",
        "missing_details": ["Measured observations"],
        "follow_up_questions": ["What else have you noticed?"],
        "physician_approval_required": True,
    }
