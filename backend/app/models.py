import time
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class WorkspaceAccount(Base):
    __tablename__ = "workspace_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="patient")
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    # Name, age, gender, contact, history, allergies, and current medicines are encrypted.
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    doctor_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="intake")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    # Contains submitted input, transcript segments, OCR references, summary, and notes.
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    __mapper_args__ = {"version_id_col": version}


class Analysis(Base):
    __tablename__ = "ai_analysis_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), index=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("ai_analysis_records.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Encrypted immutable input/report snapshot and generated PDF bytes.
    data: Mapped[bytes] = mapped_column(LargeBinary)
    pdf: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    reset_at: Mapped[float] = mapped_column(Float, index=True)
