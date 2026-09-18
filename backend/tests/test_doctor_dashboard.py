"""Dashboard counts and rows must respect doctor access and current analysis state."""

import pytest
from app.models import Analysis, Audit, Consultation, Patient
from app.security import Actor, authenticate
from sqlalchemy import select

DOCTOR = "doctor-a"


@pytest.fixture
def records(app, patient):
    def add(
        cid,
        *,
        owner=DOCTOR,
        doctor=None,
        status="intake",
        has_analysis=False,
        historical_analysis=False,
        updated_at=100,
        mode="General",
    ):
        snapshot = {**patient, "name": f"Visit {cid}", "mode": mode}
        payload = {"patient": snapshot, "transcripts": [], "documents": [], "human_summary": {}}
        if has_analysis:
            payload["analysis_id"] = f"analysis-{cid}"
        with app.state.db.sessions.begin() as session:
            session.add(Patient(
                id=f"patient-{cid}", owner_id=owner,
                data=app.state.db.seal({**snapshot, "name": "Private later patient profile"}),
            ))
            session.flush()
            session.add(Consultation(
                id=cid, patient_id=f"patient-{cid}", owner_id=owner, doctor_id=doctor,
                status=status, consent=True, data=app.state.db.seal(payload),
                created_at=1, updated_at=updated_at,
            ))
            session.flush()
            if has_analysis or historical_analysis:
                session.add(Analysis(
                    id=f"analysis-{cid}", consultation_id=cid, input_hash="test-input",
                    data=app.state.db.seal({"summary": "Synthetic analysis"}),
                ))
        return cid

    return add


@pytest.fixture
def doctor_client(app, client):
    app.dependency_overrides[authenticate] = lambda: Actor(DOCTOR, "doctor")
    return client


def test_dashboard_requires_authentication_and_doctor_role(app, client, records):
    records("owned-by-patient", owner="patient-a")
    assert client.get(
        "/api/doctor/dashboard", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401
    app.dependency_overrides[authenticate] = lambda: Actor("patient-a", "patient")
    response = client.get("/api/doctor/dashboard")
    assert response.status_code == 403
    assert "Visit owned-by-patient" not in response.text


def test_dashboard_uses_owned_and_assigned_visit_snapshots(app, doctor_client, records):
    records("owned", updated_at=20)
    records("assigned", owner="patient-a", doctor=DOCTOR, updated_at=30, mode="AYUSH")
    records("owned-and-assigned", doctor=DOCTOR, updated_at=10)
    records("private", owner="patient-a", doctor="doctor-b", updated_at=40)
    with app.state.db.sessions.begin() as session:
        # An inaccessible snapshot must not even be decrypted for counts.
        session.get(Consultation, "private").data = b"not accessible ciphertext"
    response = doctor_client.get("/api/doctor/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert [item["id"] for item in data["items"]] == ["assigned", "owned", "owned-and-assigned"]
    assert data["stats"] == {"total": 3, "pending": 0, "reviewed": 0, "rejected": 0, "draft": 3}
    assert data["items"][0] == {
        "id": "assigned", "name": "Visit assigned", "age": 32, "gender": "Female",
        "mode": "AYUSH", "status": "intake", "created_at": 1, "updated_at": 30,
        "has_analysis": False,
    }
    assert "Private later patient profile" not in response.text
    assert "symptoms" not in response.text
    with app.state.db.sessions() as session:
        audit = session.scalar(select(Audit).where(Audit.action == "doctor.dashboard.read"))
        assert audit is not None and audit.actor_id == DOCTOR


def test_dashboard_filters_current_analysis_and_preserves_whole_scope_stats(
    doctor_client, records
):
    records("new-intake", updated_at=60)
    records("edited-intake", historical_analysis=True, updated_at=50)
    records("pending-b", status="draft", has_analysis=True, updated_at=40)
    records("pending-a", status="draft", has_analysis=True, updated_at=30)
    records("accepted", status="reviewed", has_analysis=True, updated_at=20)
    records("declined", status="rejected", has_analysis=True, updated_at=10)
    expected_stats = {"total": 6, "pending": 2, "reviewed": 1, "rejected": 1, "draft": 2}
    expected_ids = {
        "all": ["new-intake", "edited-intake", "pending-b", "pending-a", "accepted", "declined"],
        "pending": ["pending-b", "pending-a"],
        "reviewed": ["accepted"],
        "rejected": ["declined"],
        "draft": ["new-intake", "edited-intake"],
    }
    for status, ids in expected_ids.items():
        response = doctor_client.get("/api/doctor/dashboard", params={"status": status})
        assert response.status_code == 200, response.text
        data = response.json()
        assert [item["id"] for item in data["items"]] == ids
        assert data["stats"] == expected_stats
        assert data["total_matches"] == len(ids)
        assert data["offset"] == 0 and data["limit"] == 10 and data["has_more"] is False


def test_dashboard_pagination_is_filtered_and_deterministic(doctor_client, records):
    for cid in ("a", "c", "b"):
        records(cid, status="draft", has_analysis=True, updated_at=100)
    records("newer-unmatched", updated_at=200)
    records("newest-pending", status="draft", has_analysis=True, updated_at=150)

    def page(offset):
        response = doctor_client.get(
            "/api/doctor/dashboard", params={"status": "pending", "offset": offset, "limit": 2}
        )
        assert response.status_code == 200, response.text
        return response.json()

    first, second, beyond = page(0), page(2), page(10)
    assert [item["id"] for item in first["items"]] == ["newest-pending", "c"]
    assert [item["id"] for item in second["items"]] == ["b", "a"]
    assert beyond["items"] == []
    assert first["has_more"] is True
    assert second["has_more"] is False and beyond["has_more"] is False
    for data, offset in ((first, 0), (second, 2), (beyond, 10)):
        assert data["total_matches"] == 4
        assert data["stats"] == {"total": 5, "pending": 4, "reviewed": 0, "rejected": 0, "draft": 1}
        assert data["offset"] == offset and data["limit"] == 2


def test_dashboard_empty_scope(doctor_client):
    response = doctor_client.get("/api/doctor/dashboard")
    assert response.status_code == 200
    assert response.json() == {
        "stats": {"total": 0, "pending": 0, "reviewed": 0, "rejected": 0, "draft": 0},
        "items": [], "offset": 0, "limit": 10, "has_more": False, "total_matches": 0,
    }


@pytest.mark.parametrize("params", [
    {"status": "unknown"}, {"offset": -1}, {"limit": 0}, {"limit": 51},
])
def test_dashboard_rejects_invalid_filters_and_pagination(doctor_client, params):
    assert doctor_client.get("/api/doctor/dashboard", params=params).status_code == 422
