import hashlib
import secrets
import time
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import RateBucket

bearer = HTTPBearer(auto_error=False)


@dataclass
class Actor:
    subject: str
    role: str


def rate_limit(db, key, maximum=60, seconds=60):
    now = time.time()
    key = hashlib.sha256(key.encode()).hexdigest()
    with db.sessions.begin() as s:
        s.execute(delete(RateBucket).where(RateBucket.reset_at < now))
        insert = sqlite_insert if db.engine.dialect.name == "sqlite" else pg_insert
        s.execute(
            insert(RateBucket)
            .values(key=key, count=1, reset_at=now + seconds)
            .on_conflict_do_update(index_elements=["key"], set_={"count": RateBucket.count + 1})
        )
        count = s.scalar(select(RateBucket.count).where(RateBucket.key == key))
    if count > maximum:
        raise HTTPException(
            429, "Too many requests. Retry later.", headers={"Retry-After": str(seconds)}
        )


async def authenticate(request: Request, credentials=Security(bearer)):
    if not credentials:
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    token = credentials.credentials
    settings = request.app.state.settings
    if settings.app_env != "production" and secrets.compare_digest(token, settings.dev_auth_token):
        role = request.headers.get("X-Care-Role", "doctor")
        actor = Actor("local-clinician", role if role in {"doctor", "patient"} else "doctor")
    else:
        if not settings.supabase_url:
            raise HTTPException(401, "Invalid access token.")
        try:
            # Only asymmetric JWTs issued by the configured project are accepted.
            from starlette.concurrency import run_in_threadpool

            key = await run_in_threadpool(request.app.state.jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256", "ES256"],
                audience="authenticated",
                issuer=settings.supabase_url.rstrip("/") + "/auth/v1",
                options={"require": ["sub", "exp", "iat", "aud", "iss"]},
            )
            metadata = claims.get("app_metadata") or {}
            role = metadata.get("care_role", "patient")
            actor = Actor(str(claims["sub"]), "doctor" if role == "doctor" else "patient")
        except Exception:
            raise HTTPException(401, "Invalid or expired access token.") from None
    rate_limit(request.app.state.db, actor.subject)
    return actor
