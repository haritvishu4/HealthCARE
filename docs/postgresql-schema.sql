BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE audit_events (
    id VARCHAR(36) NOT NULL, 
    actor_id VARCHAR(128) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    resource_id VARCHAR(128) NOT NULL, 
    created_at FLOAT NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id);

CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);

CREATE TABLE patients (
    id VARCHAR(36) NOT NULL, 
    owner_id VARCHAR(128) NOT NULL, 
    data BYTEA NOT NULL, 
    created_at FLOAT NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_patients_owner_id ON patients (owner_id);

CREATE TABLE rate_buckets (
    key VARCHAR(64) NOT NULL, 
    count INTEGER NOT NULL, 
    reset_at FLOAT NOT NULL, 
    PRIMARY KEY (key)
);

CREATE INDEX ix_rate_buckets_reset_at ON rate_buckets (reset_at);

CREATE TABLE consultations (
    id VARCHAR(36) NOT NULL, 
    patient_id VARCHAR(36) NOT NULL, 
    owner_id VARCHAR(128) NOT NULL, 
    doctor_id VARCHAR(128), 
    version INTEGER NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    consent BOOLEAN NOT NULL, 
    data BYTEA NOT NULL, 
    created_at FLOAT NOT NULL, 
    updated_at FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(patient_id) REFERENCES patients (id)
);

CREATE INDEX ix_consultations_created_at ON consultations (created_at);

CREATE INDEX ix_consultations_doctor_id ON consultations (doctor_id);

CREATE INDEX ix_consultations_owner_id ON consultations (owner_id);

CREATE INDEX ix_consultations_patient_id ON consultations (patient_id);

CREATE TABLE ai_analysis_records (
    id VARCHAR(36) NOT NULL, 
    consultation_id VARCHAR(36) NOT NULL, 
    input_hash VARCHAR(64) NOT NULL, 
    data BYTEA NOT NULL, 
    created_at FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(consultation_id) REFERENCES consultations (id)
);

CREATE INDEX ix_ai_analysis_records_consultation_id ON ai_analysis_records (consultation_id);

CREATE INDEX ix_ai_analysis_records_input_hash ON ai_analysis_records (input_hash);

CREATE TABLE documents (
    id VARCHAR(36) NOT NULL, 
    consultation_id VARCHAR(36) NOT NULL, 
    data BYTEA NOT NULL, 
    file_bytes BYTEA NOT NULL, 
    created_at FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(consultation_id) REFERENCES consultations (id)
);

CREATE INDEX ix_documents_consultation_id ON documents (consultation_id);

CREATE TABLE prescriptions (
    id VARCHAR(36) NOT NULL, 
    consultation_id VARCHAR(36) NOT NULL, 
    analysis_id VARCHAR(36) NOT NULL, 
    snapshot_hash VARCHAR(64) NOT NULL, 
    data BYTEA NOT NULL, 
    pdf BYTEA NOT NULL, 
    created_at FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(analysis_id) REFERENCES ai_analysis_records (id), 
    FOREIGN KEY(consultation_id) REFERENCES consultations (id), 
    UNIQUE (snapshot_hash)
);

CREATE INDEX ix_prescriptions_consultation_id ON prescriptions (consultation_id);

ALTER TABLE patients ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE patients FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE patients FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE patients FROM authenticated'; END IF; END $$;

ALTER TABLE consultations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE consultations FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE consultations FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE consultations FROM authenticated'; END IF; END $$;

ALTER TABLE ai_analysis_records ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE ai_analysis_records FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE ai_analysis_records FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE ai_analysis_records FROM authenticated'; END IF; END $$;

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE documents FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE documents FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE documents FROM authenticated'; END IF; END $$;

ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE prescriptions FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE prescriptions FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE prescriptions FROM authenticated'; END IF; END $$;

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE audit_events FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE audit_events FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE audit_events FROM authenticated'; END IF; END $$;

ALTER TABLE rate_buckets ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE rate_buckets FROM PUBLIC;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE 'REVOKE ALL ON TABLE rate_buckets FROM anon'; END IF; END $$;

DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE 'REVOKE ALL ON TABLE rate_buckets FROM authenticated'; END IF; END $$;

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

