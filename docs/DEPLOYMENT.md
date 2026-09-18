# Deployment foundation

This project runs locally and supplies production-oriented controls. Public healthcare deployment still needs real identity integration, infrastructure operations, and clinical validation. It has not been certified for medical use or assessed for jurisdiction-specific compliance.

## Authentication

The bundled local frontend server binds to `127.0.0.1`, rejects unrelated hosts/origins, and requires a workspace login before proxying API requests or API documentation. First-time setup saves a salted scrypt password hash in `backend/.local-auth.json`. Login issues an HttpOnly, SameSite=Strict cookie with an eight-hour session; logout and server restart revoke sessions. Only authenticated proxy requests receive the private local backend token. This account retains the existing development clinician identity and access to saved records. It is for a trusted local computer only. Do not expose this development server with a tunnel or publish its token.

For a hosted deployment, replace the local `auth.js` bootstrap in `frontend/index.html` with your production authentication host. After verifying sign-in, supply the user's Supabase access token in memory as `window.CARE_ACCESS_TOKEN`, set `window.CARE_API_BASE` to your HTTPS API origin if it differs, and load `icons.js`, `state.js`, `helpers.js`, `views.js`, `app.js`, `api.js`, `dashboard.js`, and `integration.js` in that order. Remove the initial `auth-mode` body class when opening the workspace. Your host must keep the token refreshed, handle expired sessions, and clear it and patient state on sign-out. The optional `CareAuth` interface used by the UI is `user: {name, email}`, `logout()`, and `expireSession()`; implement these with the production host if using the bundled profile/sign-out controls. Do not store bearer tokens in localStorage or embed fixed tokens in source. The included `/auth/*` routes are local workspace authentication, not Supabase patient/doctor accounts.

Use asymmetric Supabase JWT signing keys. The backend verifies the configured project's JWKS, issuer, audience, expiry, and signature. Set `app_metadata.care_role = "doctor"` only through your trusted server/admin process after verifying a clinician. Never infer doctor privilege from user-editable `user_metadata`. Everyone else is a patient. Ownership and an explicit consultation doctor assignment control resource access. A patient creating several profiles should be restricted further in your host if family/caregiver profiles are not part of your product.

Configure at least:

```dotenv
APP_ENV=production
DEV_AUTH_TOKEN=
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
DATABASE_URL=postgresql+psycopg://BACKEND_DB_ROLE:PASSWORD@DB_HOST:5432/postgres?sslmode=require
FIELD_ENCRYPTION_KEY=YOUR_EXISTING_PRIVATE_ENCRYPTION_KEY
ALLOWED_ORIGINS=["https://your-ui.example"]
ALLOWED_HOSTS=["your-api.example"]
DOCS_ENABLED=false
```

Store secrets in the hosting provider's secret manager. Use TLS and verify database certificates according to the database host's settings. Preserve and back up the encryption key separately from database backups. This version uses one Fernet key; plan a versioned rotation/migration process before rotation. Losing it makes clinical data unreadable.

## Run and migrate

Install `backend/requirements.txt` and run migrations once as a deployment step:

```bash
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 2 --no-access-log
```

Terminate HTTPS at a configured reverse proxy. Set a request-body limit at the proxy, authenticate/rate-limit unauthenticated traffic at the edge, and restrict database access to the backend network. Keep docs disabled externally. Forward identity only through verified JWTs, never a trusted-looking user ID header.

`backend/Dockerfile` builds a non-root API image. The optional `container-api` profile in `compose.yaml` is a local development configuration:

```bash
python3 scripts/setup.py --skip-install
docker compose up -d db
docker compose --profile container-api build api
docker compose --profile container-api run --rm api python -m alembic upgrade head
docker compose --profile container-api up -d api
python3 scripts/frontend_server.py
```

Do not run `scripts/run.py` at the same time as the container API on port 8000. Local Compose credentials are intentionally recognizable development values. Change them and use managed secrets before deployment.

## Data and scaling

SQLAlchemy foreign keys link patients, consultations, analyses, documents, and draft prescriptions. IDs/ownership/version/timestamps are queryable metadata. Clinical fields and document/PDF bytes are encrypted in `data`/binary columns. This deliberately avoids plaintext name, symptom, or `pdf_path` columns. Migrations create RLS without browser access policies on PostgreSQL and revoke clinical-table grants from Supabase browser roles. The backend's dedicated table-owning DB role accesses them; do not expose this role to browsers.

Optimistic versions reject stale updates. Immutable prescription snapshots preserve earlier drafts after later edits. Patient history uses scoped queries and separates reviewed notes from unverified patient reports. Audit events store actor/action/resource/time, not medical text. The audit table is application-managed, not a tamper-proof compliance archive.

For larger workloads, move document/PDF bytes behind a private object-storage abstraction with scoped short-lived downloads; run OCR/parsing in isolated background workers; use a shared queue and distributed concurrency controls; and define retention/deletion, recovery, observability, dependency updates, backup/restore drills, and incident response. The synchronous draft workflow and per-process provider semaphore in this release are suitable foundations, not an unbounded processing pipeline.

## Clinical and provider validation

Gemini is instructed to produce uncertain clinical assistance only. The server validates structure, requires the physician-approval flag, records provenance, and stamps every PDF as a draft. Prompting and schema checks cannot guarantee medical accuracy or prevent every unsafe model response. Validate the selected model, representative languages, negations, emergencies, allergy mentions, OCR errors, hallucinations, and prompt injection with clinicians before use. There is no independently validated triage algorithm, signed prescription, medication interaction engine, automatic dosing, ABHA/ABDM integration, or radiology diagnosis.

Consent identifies which external services receive data. Names/contact fields are omitted from the structured Gemini patient block, but free text and scans may contain identifiers. Configure appropriate provider accounts, retention, residency, and contractual terms for your intended use. OCR.space is a pluggable text extraction adapter; it has not been qualified here as a specialist medical OCR service.

Bundled DejaVu and Noto fonts with HarfBuzz cover English and multiple Indian scripts. Validate typography for every language you deploy, especially mixed right-to-left text. The PDF service rejects unsupported glyphs rather than silently replacing patient text with boxes. Browser inputs/transcripts preserve the original Unicode text.
