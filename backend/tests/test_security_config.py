import time
from types import SimpleNamespace

import jwt
import pytest
from app.config import Settings
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError


def test_jwt_signature_issuer_expiry_and_server_managed_role(app, client):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app.state.settings.supabase_url = "https://test-project.supabase.co"
    app.state.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    )
    claims = {
        "sub": "test-patient",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
        "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
        "user_metadata": {"care_role": "doctor"},
    }

    def get(data, signing_key=key):
        token = jwt.encode(data, signing_key, algorithm="RS256")
        return client.get("/api/system", headers={"Authorization": "Bearer " + token})

    assert get(claims).json()["role"] == "patient"
    assert get({**claims, "app_metadata": {"care_role": "doctor"}}).json()["role"] == "doctor"
    assert get({**claims, "exp": 1}).status_code == 401
    assert (
        get({**claims, "iss": "https://different-project.supabase.co/auth/v1"}).status_code == 401
    )
    assert get({**claims, "aud": "other"}).status_code == 401
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert get(claims, other).status_code == 401


def test_production_rejects_dev_bypass_and_insecure_configuration(app):
    data = app.state.settings.model_dump()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "app_env": "production"})
    data.update(
        app_env="production",
        dev_auth_token="",
        supabase_url="https://test.supabase.co",
        database_url="postgresql://user:pass@localhost/database",
        docs_enabled=False,
        allowed_origins=["https://care.example"],
        allowed_hosts=["api.care.example"],
    )
    configured = Settings(_env_file=None, **data)
    assert configured.database_url.startswith("postgresql+psycopg://")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "allowed_origins": ["http://localhost:5173"]})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**data, "dev_auth_token": "x" * 40})
