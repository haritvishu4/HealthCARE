import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import jwt
from cryptography.fernet import InvalidToken
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse as StarletteJSON

from .config import get_settings
from .database import Database
from .models import Analysis, Consultation, Document, Patient, Prescription, uid
from .schemas import (
    AnalyzeRequest,
    ConsentRequest,
    IntakeRequest,
    PDFRequest,
    ReviewRequest,
    ShareRequest,
    SummaryRequest,
)
from .security import Actor, authenticate, rate_limit
from .services.files import audio_type, document_type, read_upload, safe_name
from .services.gemini_service import analyze_patient
from .services.ocr_service import extract_medical_text
from .services.pdf_service import generate_prescription_pdf
from .services.provider import ServiceError
from .services.sarvam_service import LANGUAGES, convert_audio_to_text


def checksum(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class BodyLimit:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length:
            try:
                if int(length) > self.max_bytes:
                    return await StarletteJSON(
                        {"detail": "Request body is too large."}, status_code=413
                    )(scope, receive, send)
            except ValueError:
                return await StarletteJSON({"detail": "Invalid content length."}, status_code=400)(
                    scope, receive, send
                )
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise HTTPException(413, "Request body is too large.")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings=None):
    settings = settings or get_settings()
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        app.state.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout, connect=10),
            limits=httpx.Limits(max_connections=20),
        )
        yield
        await app.state.client.aclose()
        db.engine.dispose()

    app = FastAPI(
        title="Care Intake API",
        version="1.0.0",
        lifespan=lifespan,
        description="Authenticated patient intake and AI-assisted clinical drafts. Not a diagnostic or autonomous prescribing service.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.db, app.state.settings = db, settings
    app.state.provider_slots = asyncio.Semaphore(4)
    if settings.supabase_url:
        app.state.jwks = jwt.PyJWKClient(
            settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json", lifespan=300
        )
    app.add_middleware(BodyLimit, max_bytes=settings.max_upload_bytes + 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ServiceError)
    async def provider_error(_, exc):
        return JSONResponse(
            {"detail": exc.message, "provider": exc.provider}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return JSONResponse(
            {
                "detail": "Invalid input.",
                "errors": [
                    {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
                    for e in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.exception_handler(StaleDataError)
    async def stale_error(_, exc):
        return JSONResponse(
            {"detail": "This record changed. Reload before saving."}, status_code=409
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_, exc):
        return JSONResponse(
            {"detail": "A conflicting record already exists. Reload and retry."}, status_code=409
        )

    @app.exception_handler(InvalidToken)
    async def encryption_error(_, exc):
        return JSONResponse(
            {
                "detail": "The encryption key cannot open this record. Restore the original FIELD_ENCRYPTION_KEY from your backup."
            },
            status_code=503,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_, exc):
        return JSONResponse(
            {"detail": "Database unavailable. Check DATABASE_URL and run migrations."},
            status_code=503,
        )

    def consultation(s, cid, actor, owner_only=False):
        c = s.get(Consultation, cid)
        if not c or (
            c.owner_id != actor.subject
            and (owner_only or actor.role != "doctor" or c.doctor_id != actor.subject)
        ):
            raise HTTPException(404, "Consultation not found.")
        return c

    def expect(c, version):
        if version is None or c.version != version:
            raise HTTPException(409, "This record changed. Reload before saving.")

    def ensure_consent(c):
        if not c.consent:
            raise HTTPException(
                403, "Consent is required for external AI, speech, and OCR processing."
            )

    def invalidate(payload):
        payload.pop("analysis_id", None)
        payload.pop("review", None)
        payload["human_summary"] = {}

    def save_payload(c, payload):
        c.data = db.seal(payload)
        c.updated_at = time.time()

    def serialize(c):
        payload = db.open(c.data)
        return {
            "id": c.id,
            "patient_id": c.patient_id,
            "owner_id": c.owner_id,
            "version": c.version,
            "status": c.status,
            "consent": c.consent,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "doctor_id": c.doctor_id,
            **payload,
        }

    def prior_records(s, c, actor):
        query = (
            select(Consultation)
            .where(
                Consultation.patient_id == c.patient_id,
                Consultation.id != c.id,
                or_(
                    Consultation.owner_id == actor.subject, Consultation.doctor_id == actor.subject
                ),
            )
            .order_by(Consultation.created_at.desc())
            .limit(5)
        )
        records = []
        for old in s.scalars(query):
            data = db.open(old.data)
            old_patient = data["patient"]
            records.append(
                {
                    "date": old.created_at,
                    "symptoms": old_patient.get("symptoms"),
                    "medical_history": old_patient.get("medical_history"),
                    "allergies": old_patient.get("allergies"),
                    "current_medicines": old_patient.get("current_medicines"),
                    "reviewed_notes": data.get("review", {}).get("doctor_notes")
                    if old.status == "reviewed"
                    else None,
                    "source": "Previous patient-reported information; not a verified diagnosis.",
                }
            )
        return records

    @app.get("/health", tags=["System"])
    def health():
        with db.sessions() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/system", tags=["System"])
    def system(actor: Actor = Depends(authenticate)):
        return {
            "mode": settings.app_env,
            "actor": actor.subject,
            "role": actor.role,
            "providers": {
                "gemini": bool(settings.gemini_api_key),
                "sarvam": bool(settings.sarvam_api_key),
                "ocr": bool(settings.ocr_api_key),
            },
            "speech_languages": sorted(LANGUAGES),
            "max_upload_bytes": settings.max_upload_bytes,
            "draft_only": True,
        }

    @app.post("/api/patient/intake", tags=["Patients"])
    def intake(body: IntakeRequest, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            details = body.patient.model_dump()
            if body.consultation_id:
                c = consultation(s, body.consultation_id, actor, owner_only=True)
                expect(c, body.expected_version)
                if body.patient_id and body.patient_id != c.patient_id:
                    raise HTTPException(422, "Patient and consultation do not match.")
                p = s.get(Patient, c.patient_id)
                payload = db.open(c.data)
                if payload["patient"] != details:
                    invalidate(payload)
                    c.status = "intake"
                payload["patient"] = details
                c.consent = body.consent
                save_payload(c, payload)
            else:
                if body.patient_id:
                    p = s.get(Patient, body.patient_id)
                    if not p or p.owner_id != actor.subject:
                        raise HTTPException(404, "Patient not found.")
                else:
                    p = Patient(id=uid(), owner_id=actor.subject, data=db.seal(details))
                    s.add(p)
                    s.flush()
                c = Consultation(
                    id=uid(),
                    patient_id=p.id,
                    owner_id=actor.subject,
                    consent=body.consent,
                    data=db.seal(
                        {
                            "patient": details,
                            "transcripts": [],
                            "documents": [],
                            "human_summary": {},
                        }
                    ),
                )
                s.add(c)
            p.data = db.seal(details)
            db.audit(s, actor.subject, "intake.save", c.id)
            s.flush()
            return {
                "patient_id": p.id,
                "consultation_id": c.id,
                "version": c.version,
                "status": c.status,
            }

    @app.get("/api/patients", tags=["Patients"])
    def patients(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        actor: Actor = Depends(authenticate),
    ):
        with db.sessions() as s:
            rows = s.scalars(
                select(Patient)
                .where(Patient.owner_id == actor.subject)
                .order_by(Patient.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [
                    {"id": p.id, "created_at": p.created_at, **db.open(p.data)} for p in rows
                ],
                "offset": offset,
                "limit": limit,
            }

    @app.get("/api/patient/{patient_id}/history", tags=["Patients"])
    def history(
        patient_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        actor: Actor = Depends(authenticate),
    ):
        with db.sessions.begin() as s:
            p = s.get(Patient, patient_id)
            scope = Consultation.owner_id == actor.subject
            if actor.role == "doctor":
                scope = or_(scope, Consultation.doctor_id == actor.subject)
            query = select(Consultation).where(Consultation.patient_id == patient_id, scope)
            rows = list(
                s.scalars(
                    query.order_by(Consultation.created_at.desc()).offset(offset).limit(limit)
                )
            )
            if not p or (p.owner_id != actor.subject and not rows):
                raise HTTPException(404, "Patient not found.")
            items = []
            for c in rows:
                value = serialize(c)
                value["prescriptions"] = [
                    {
                        "id": x.id,
                        "created_at": x.created_at,
                        "download_url": f"/api/prescription/{x.id}/download",
                        "draft": True,
                    }
                    for x in s.scalars(
                        select(Prescription)
                        .where(Prescription.consultation_id == c.id)
                        .order_by(Prescription.created_at.desc())
                    )
                ]
                items.append(value)
            db.audit(s, actor.subject, "history.read", patient_id)
            visible_profile = (
                db.open(p.data) if p.owner_id == actor.subject else db.open(rows[0].data)["patient"]
            )
            return {
                "patient": {"id": p.id, **visible_profile},
                "items": items,
                "offset": offset,
                "limit": limit,
            }

    @app.get("/api/consultation/{cid}", tags=["Consultations"])
    def get_consultation(cid: str, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            c = consultation(s, cid, actor)
            result = serialize(c)
            aid = result.get("analysis_id")
            analysis = s.get(Analysis, aid) if aid else None
            result["ai_analysis"] = db.open(analysis.data) if analysis else None
            db.audit(s, actor.subject, "consultation.read", cid)
            return result

    @app.get("/api/consultations", tags=["Consultations"])
    def list_consultations(
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        actor: Actor = Depends(authenticate),
    ):
        with db.sessions.begin() as s:
            scope = Consultation.owner_id == actor.subject
            if actor.role == "doctor":
                scope = or_(scope, Consultation.doctor_id == actor.subject)
            rows = list(
                s.scalars(
                    select(Consultation)
                    .where(scope)
                    .order_by(Consultation.created_at.desc())
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            items = [
                {
                    "id": c.id,
                    "patient_id": c.patient_id,
                    "name": db.open(c.data)["patient"]["name"],
                    "created_at": c.created_at,
                    "status": c.status,
                }
                for c in rows[:limit]
            ]
            db.audit(s, actor.subject, "consultations.list", actor.subject)
            return {"items": items, "offset": offset, "limit": limit, "has_more": len(rows) > limit}

    @app.get("/api/doctor/dashboard", tags=["Doctor"])
    def doctor_dashboard(
        status: Literal["all", "pending", "reviewed", "rejected", "draft"] = "all",
        offset: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=50),
        actor: Actor = Depends(authenticate),
    ):
        if actor.role != "doctor":
            raise HTTPException(403, "A doctor account is required to view this dashboard.")
        stats = {"total": 0, "pending": 0, "reviewed": 0, "rejected": 0, "draft": 0}
        items = []
        total_matches = 0
        with db.sessions.begin() as s:
            rows = s.scalars(
                select(Consultation)
                .where(
                    or_(
                        Consultation.owner_id == actor.subject,
                        Consultation.doctor_id == actor.subject,
                    )
                )
                .order_by(Consultation.updated_at.desc(), Consultation.id.desc())
                .execution_options(yield_per=100)
            )
            # The active analysis reference lives in the encrypted snapshot. Scan
            # only accessible consultations and retain just the requested page.
            for c in rows:
                payload = db.open(c.data)
                has_analysis = bool(payload.get("analysis_id"))
                if not has_analysis:
                    category = "draft"
                elif c.status in ("reviewed", "rejected"):
                    category = c.status
                else:
                    category = "pending"
                stats["total"] += 1
                stats[category] += 1
                if status != "all" and status != category:
                    continue
                total_matches += 1
                if offset < total_matches <= offset + limit:
                    patient = payload["patient"]
                    items.append(
                        {
                            "id": c.id,
                            "name": patient["name"],
                            "age": patient["age"],
                            "gender": patient["gender"],
                            "mode": patient.get("mode", "General"),
                            "status": c.status,
                            "created_at": c.created_at,
                            "updated_at": c.updated_at,
                            "has_analysis": has_analysis,
                        }
                    )
            db.audit(s, actor.subject, "doctor.dashboard.read", actor.subject)
        return {
            "stats": stats,
            "items": items,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < total_matches,
            "total_matches": total_matches,
        }

    @app.patch("/api/consultation/{cid}/summary", tags=["Consultations"])
    def save_summary(cid: str, body: SummaryRequest, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            c = consultation(s, cid, actor)
            expect(c, body.expected_version)
            payload = db.open(c.data)
            if not payload.get("analysis_id"):
                raise HTTPException(409, "Generate an analysis before amending the draft.")
            if payload.get("human_summary", {}) == body.summary:
                return {"version": c.version, "status": c.status}
            payload["human_summary"] = body.summary
            payload.pop("review", None)
            c.status = "draft"
            save_payload(c, payload)
            db.audit(s, actor.subject, "summary.amend", cid)
            s.flush()
            return {"version": c.version, "status": c.status}

    @app.post("/api/consultation/{cid}/review", tags=["Consultations"])
    def review(cid: str, body: ReviewRequest, actor: Actor = Depends(authenticate)):
        if actor.role != "doctor":
            raise HTTPException(403, "A doctor account is required to record a review.")
        with db.sessions.begin() as s:
            c = consultation(s, cid, actor)
            expect(c, body.expected_version)
            payload = db.open(c.data)
            if not payload.get("analysis_id"):
                raise HTTPException(409, "Generate an analysis before review.")
            payload["human_summary"] = body.summary
            payload["review"] = {
                "decision": body.decision,
                "doctor_notes": body.doctor_notes,
                "actor": actor.subject,
                "at": time.time(),
            }
            c.status = "reviewed" if body.decision == "accept" else "rejected"
            save_payload(c, payload)
            db.audit(s, actor.subject, "review." + body.decision, cid)
            s.flush()
            return {"version": c.version, "status": c.status, "draft_only": True}

    @app.post("/api/consultation/{cid}/share", tags=["Consultations"])
    def share(cid: str, body: ShareRequest, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            c = consultation(s, cid, actor, owner_only=True)
            expect(c, body.expected_version)
            c.doctor_id = body.doctor_id
            db.audit(s, actor.subject, "share.update", cid)
            s.flush()
            return {"version": c.version, "doctor_id": c.doctor_id}

    @app.patch("/api/consultation/{cid}/consent", tags=["Consultations"])
    def consent(cid: str, body: ConsentRequest, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            c = consultation(s, cid, actor, owner_only=True)
            expect(c, body.expected_version)
            c.consent = body.consent
            if not c.consent:
                c.doctor_id = None
            db.audit(s, actor.subject, "consent.grant" if c.consent else "consent.revoke", cid)
            s.flush()
            return {"version": c.version, "consent": c.consent}

    @app.post("/api/audio/transcribe", tags=["Speech"])
    async def transcribe(
        request: Request,
        consultation_id: str = Form(...),
        expected_version: int = Form(...),
        language: str = Form("unknown"),
        file: UploadFile = File(...),
        actor: Actor = Depends(authenticate),
    ):
        rate_limit(db, actor.subject + ":speech", 20)
        with db.sessions() as s:
            c = consultation(s, consultation_id, actor, owner_only=True)
            expect(c, expected_version)
            ensure_consent(c)
        data = await read_upload(file, settings.max_upload_bytes)
        mime, extension = audio_type(data)
        async with app.state.provider_slots:
            result = await convert_audio_to_text(
                data,
                settings=settings,
                client=app.state.client,
                language=language,
                filename="speech." + extension,
                content_type=mime,
            )
        with db.sessions.begin() as s:
            c = consultation(s, consultation_id, actor, owner_only=True)
            expect(c, expected_version)
            ensure_consent(c)
            payload = db.open(c.data)
            if len(payload["transcripts"]) >= 30:
                raise HTTPException(422, "Recording limit reached for this consultation.")
            payload["transcripts"].append(
                {
                    "text": result["text"],
                    "language_code": result["language_code"],
                    "created_at": time.time(),
                }
            )
            invalidate(payload)
            c.status = "intake"
            save_payload(c, payload)
            db.audit(s, actor.subject, "audio.transcribe", c.id)
            s.flush()
            return {**result, "version": c.version}

    @app.post("/api/document/upload", tags=["Documents"])
    async def upload(
        consultation_id: str = Form(...),
        expected_version: int = Form(...),
        file: UploadFile = File(...),
        actor: Actor = Depends(authenticate),
    ):
        rate_limit(db, actor.subject + ":ocr", 10)
        with db.sessions() as s:
            c = consultation(s, consultation_id, actor, owner_only=True)
            expect(c, expected_version)
            ensure_consent(c)
            if len(db.open(c.data)["documents"]) >= 20:
                raise HTTPException(422, "Document limit reached for this consultation.")
        filename = safe_name(file.filename)
        data = await read_upload(file, settings.max_upload_bytes)
        mime = await run_in_threadpool(document_type, data)
        async with app.state.provider_slots:
            result = await extract_medical_text(
                data,
                settings=settings,
                client=app.state.client,
                filename=filename,
                content_type=mime,
            )
        with db.sessions.begin() as s:
            c = consultation(s, consultation_id, actor, owner_only=True)
            expect(c, expected_version)
            ensure_consent(c)
            did = uid()
            metadata = {**result, "filename": filename, "content_type": mime, "size": len(data)}
            s.add(
                Document(
                    id=did,
                    consultation_id=c.id,
                    data=db.seal(metadata),
                    file_bytes=db.cipher.encrypt(data),
                )
            )
            payload = db.open(c.data)
            payload["documents"].append(
                {
                    "id": did,
                    "name": filename,
                    "size": len(data),
                    "text": result["text"],
                    "document_type": result["document_type"],
                    "confidence": result["confidence"],
                }
            )
            invalidate(payload)
            c.status = "intake"
            save_payload(c, payload)
            db.audit(s, actor.subject, "document.upload", did)
            s.flush()
            return {
                "id": did,
                "name": filename,
                "extracted_text": result["text"],
                **result,
                "version": c.version,
            }

    @app.delete("/api/document/{did}", tags=["Documents"])
    def delete_document(did: str, expected_version: int, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            d = s.get(Document, did)
            if not d:
                raise HTTPException(404, "Document not found.")
            c = consultation(s, d.consultation_id, actor, owner_only=True)
            expect(c, expected_version)
            payload = db.open(c.data)
            payload["documents"] = [x for x in payload["documents"] if x["id"] != did]
            invalidate(payload)
            c.status = "intake"
            save_payload(c, payload)
            s.delete(d)
            db.audit(s, actor.subject, "document.delete", did)
            s.flush()
            return {"version": c.version}

    @app.get("/api/document/{did}/download", tags=["Documents"])
    def download_document(did: str, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            d = s.get(Document, did)
            if not d:
                raise HTTPException(404, "Document not found.")
            consultation(s, d.consultation_id, actor)
            metadata = db.open(d.data)
            db.audit(s, actor.subject, "document.download", did)
            extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[
                metadata["content_type"]
            ]
            return Response(
                db.cipher.decrypt(d.file_bytes),
                media_type=metadata["content_type"],
                headers={
                    "Content-Disposition": f'attachment; filename="document-{did}.{extension}"'
                },
            )

    @app.post("/api/ai/analyze", tags=["AI"])
    async def analyze(body: AnalyzeRequest, actor: Actor = Depends(authenticate)):
        rate_limit(db, actor.subject + ":analysis", 8)
        with db.sessions() as s:
            c = consultation(s, body.consultation_id, actor)
            expect(c, body.expected_version)
            ensure_consent(c)
            payload = db.open(c.data)
            patient = {k: v for k, v in payload["patient"].items() if k not in ("name", "contact")}
            if not patient.get("symptoms") and not payload["transcripts"] and not body.transcript:
                raise HTTPException(422, "Provide symptoms or a transcript before analysis.")
            context = {
                "patient": patient,
                "transcripts": [x["text"] for x in payload["transcripts"]]
                + ([body.transcript] if body.transcript else []),
                "document_text": [x["text"] for x in payload["documents"]]
                + ([body.ocr_text] if body.ocr_text else []),
                "previous_patient_history": prior_records(s, c, actor),
            }
            if len(json.dumps(context, ensure_ascii=False)) > 100000:
                raise HTTPException(422, "Context is too large. Use fewer documents.")
            fingerprint = checksum(context)
            previous = s.scalar(
                select(Analysis)
                .where(Analysis.consultation_id == c.id, Analysis.input_hash == fingerprint)
                .order_by(Analysis.created_at.desc())
            )
            cached = db.open(previous.data) if previous else None
            previous_id = previous.id if previous else None
        if cached is None:
            async with app.state.provider_slots:
                report = await analyze_patient(context, settings=settings, client=app.state.client)
        else:
            report = cached
        with db.sessions.begin() as s:
            c = consultation(s, body.consultation_id, actor)
            expect(c, body.expected_version)
            ensure_consent(c)
            aid = previous_id or uid()
            if not previous_id:
                s.add(
                    Analysis(
                        id=aid, consultation_id=c.id, input_hash=fingerprint, data=db.seal(report)
                    )
                )
            payload = db.open(c.data)
            if payload.get("analysis_id") != aid:
                payload.pop("review", None)
                payload["human_summary"] = {}
            payload["analysis_id"] = aid
            payload["additional_analysis_input"] = {
                "transcript": body.transcript,
                "ocr_text": body.ocr_text,
            }
            if not payload.get("review"):
                c.status = "draft"
            save_payload(c, payload)
            db.audit(s, actor.subject, "ai.analyze", aid)
            s.flush()
            return {
                **report,
                "analysis_id": aid,
                "version": c.version,
                "provider": "gemini",
                "cached": cached is not None,
            }

    @app.post("/api/prescription/generate", tags=["Draft PDFs"])
    def generate(body: PDFRequest, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            c = consultation(s, body.consultation_id, actor)
            expect(c, body.expected_version)
            payload = db.open(c.data)
            if payload.get("analysis_id") != body.analysis_id:
                raise HTTPException(409, "Generate or select the current analysis first.")
            a = s.get(Analysis, body.analysis_id)
            if not a or a.consultation_id != c.id:
                raise HTTPException(404, "Analysis not found.")
            snapshot = {
                "patient_id": c.patient_id,
                "consultation_id": c.id,
                "patient": payload["patient"],
                "report": db.open(a.data),
                "human_summary": payload.get("human_summary", {}),
                "review": payload.get("review"),
                "analysis_id": a.id,
            }
            fingerprint = checksum(snapshot)
            previous = s.scalar(
                select(Prescription).where(Prescription.snapshot_hash == fingerprint)
            )
            if previous:
                return {
                    "id": previous.id,
                    "pdf_url": f"/api/prescription/{previous.id}/download",
                    "draft": True,
                }
            pid = uid()
            snapshot.update({"id": pid, "created_at": time.time()})
            pdf = generate_prescription_pdf(snapshot)
            s.add(
                Prescription(
                    id=pid,
                    consultation_id=c.id,
                    analysis_id=a.id,
                    snapshot_hash=fingerprint,
                    data=db.seal(snapshot),
                    pdf=db.cipher.encrypt(pdf),
                )
            )
            db.audit(s, actor.subject, "draft_pdf.generate", pid)
            return {"id": pid, "pdf_url": f"/api/prescription/{pid}/download", "draft": True}

    @app.get("/api/prescription/{pid}/download", tags=["Draft PDFs"])
    def download_pdf(pid: str, actor: Actor = Depends(authenticate)):
        with db.sessions.begin() as s:
            p = s.get(Prescription, pid)
            if not p:
                raise HTTPException(404, "PDF not found.")
            consultation(s, p.consultation_id, actor)
            db.audit(s, actor.subject, "draft_pdf.download", pid)
            return Response(
                db.cipher.decrypt(p.pdf),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="Care-Draft-{pid}.pdf"'},
            )

    return app
