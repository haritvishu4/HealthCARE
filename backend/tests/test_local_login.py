"""The local UI must authenticate before its proxy attaches the backend token."""

import importlib
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

ACCOUNT = {
    "name": "Test Clinician",
    "email": "clinician@example.test",
    "password": "Test-workspace-password-42!",
}
BACKEND_TOKEN = "test-proxy-token-" + "x" * 40


@pytest.fixture
def auth_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("local_auth")


@pytest.fixture
def clock():
    return [1_000_000.0]


@pytest.fixture
def auth(auth_module, tmp_path, clock):
    return auth_module.LocalAuth(tmp_path / "account.json", clock=lambda: clock[0])


def test_account_persists_only_credentials_and_restarts_without_sessions(
    auth, auth_module, tmp_path, clock
):
    token = auth.setup(ACCOUNT)
    account_file = tmp_path / "account.json"
    contents = account_file.read_text()
    assert auth.configured
    assert ACCOUNT["password"] not in contents
    assert token not in contents
    assert stat.S_IMODE(account_file.stat().st_mode) == 0o600
    assert auth.user(token) == {"name": ACCOUNT["name"], "email": ACCOUNT["email"]}

    restarted = auth_module.LocalAuth(account_file, clock=lambda: clock[0])
    assert restarted.configured
    assert restarted.user(token) is None
    replacement = restarted.login({"email": ACCOUNT["email"], "password": ACCOUNT["password"]})
    assert replacement != token
    assert restarted.user(replacement) == auth.user(token)


def test_second_setup_cannot_replace_the_workspace_account(auth, auth_module, tmp_path):
    auth.setup(ACCOUNT)
    before = (tmp_path / "account.json").read_bytes()
    with pytest.raises(auth_module.AuthError) as error:
        auth.setup({**ACCOUNT, "email": "different@example.test"})
    assert error.value.status == 409
    assert (tmp_path / "account.json").read_bytes() == before


def test_concurrent_setup_creates_exactly_one_account(auth_module, tmp_path):
    path = tmp_path / "account.json"
    stores = [auth_module.LocalAuth(path), auth_module.LocalAuth(path)]

    def setup(index):
        try:
            stores[index].setup({**ACCOUNT, "email": f"clinician{index}@example.test"})
            return 201
        except auth_module.AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(setup, range(2))) == [201, 409]
    assert auth_module.LocalAuth(path).configured


def test_failed_account_write_leaves_setup_recoverable(auth, auth_module, tmp_path, monkeypatch):
    def fail_write(_):
        raise OSError("Test disk failure")

    with monkeypatch.context() as patch:
        patch.setattr(auth_module.os, "fsync", fail_write)
        with pytest.raises(auth_module.AuthError) as error:
            auth.setup(ACCOUNT)
        assert error.value.status == 503
    assert not auth.configured
    assert list(tmp_path.iterdir()) == []
    assert auth.user(auth.setup(ACCOUNT))


@pytest.mark.parametrize("contents", ["not JSON", "{}", '{"email":"attacker@example.test"}'])
def test_existing_corrupt_account_fails_closed(auth_module, tmp_path, contents):
    path = tmp_path / "account.json"
    path.write_text(contents)
    with pytest.raises(RuntimeError):
        auth_module.LocalAuth(path)
    assert path.read_text() == contents


def test_wrong_password_and_unknown_email_share_a_generic_error(auth, auth_module):
    auth.setup(ACCOUNT)
    errors = []
    for credentials in (
        {"email": ACCOUNT["email"], "password": "incorrect-password"},
        {"email": "unknown@example.test", "password": ACCOUNT["password"]},
    ):
        with pytest.raises(auth_module.AuthError) as error:
            auth.login(credentials)
        errors.append((error.value.status, error.value.message))
    assert errors[0] == errors[1]
    assert errors[0][0] == 401


def test_logout_and_expiry_revoke_sessions(auth, clock):
    token = auth.setup(ACCOUNT)
    auth.logout(token)
    assert auth.user(token) is None
    assert auth.user("forged-session") is None
    token = auth.login(ACCOUNT)
    clock[0] += 8 * 60 * 60 + 1
    assert auth.user(token) is None


def test_failed_logins_are_throttled_and_recover_after_the_window(auth, auth_module, clock):
    auth.setup(ACCOUNT)
    for _ in range(5):
        with pytest.raises(auth_module.AuthError) as error:
            auth.login({**ACCOUNT, "password": "incorrect-password"}, client="test-client")
        assert error.value.status == 401
    with pytest.raises(auth_module.AuthError) as error:
        auth.login(ACCOUNT, client="test-client")
    assert error.value.status == 429
    clock[0] += 301
    assert auth.user(auth.login(ACCOUNT, client="test-client"))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""}, {"email": "invalid-email"}, {"password": "short"},
        {"password": "x" * 513}, {"password": "test-password-\ud800"},
    ],
)
def test_setup_rejects_invalid_account_input(auth, auth_module, changes):
    with pytest.raises(auth_module.AuthError) as error:
        auth.setup({**ACCOUNT, **changes})
    assert error.value.status == 400
    assert not auth.configured


@pytest.fixture
def local_server(auth):
    frontend_server = importlib.import_module("frontend_server")
    forwarded = []

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            forwarded.append({"path": self.path, "headers": dict(self.headers)})
            data = b'{"upstream":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    server = frontend_server.create_server(
        {"DEV_AUTH_TOKEN": BACKEND_TOKEN},
        auth,
        port=0,
        upstream_port=upstream.server_port,
    )
    threads = [
        Thread(target=s.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        for s in (upstream, server)
    ]
    for thread in threads:
        thread.start()

    def request(method, path, payload=None, body=None, headers=None):
        request_headers = {"Host": f"localhost:{server.server_port}"}
        if method not in ("GET", "HEAD"):
            request_headers["Origin"] = "http://" + request_headers["Host"]
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request_headers = {key: value for key, value in request_headers.items() if value is not None}
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            response_headers = dict(response.getheaders())
            parsed = json.loads(data) if data and "application/json" in response_headers.get(
                "Content-Type", ""
            ) else data
            return response.status, parsed, response_headers
        finally:
            connection.close()

    try:
        yield request, forwarded
    finally:
        for server_instance in (server, upstream):
            server_instance.shutdown()
            server_instance.server_close()
        for thread in threads:
            thread.join(timeout=2)


def session_cookie(headers):
    cookies = SimpleCookie()
    cookies.load(headers["Set-Cookie"])
    return cookies["care_session"]


def test_public_session_and_assets_do_not_require_a_login(local_server):
    request, forwarded = local_server
    status, data, _ = request("GET", "/auth/session")
    assert status == 200
    assert data == {"configured": False, "authenticated": False, "user": None}
    assert request("GET", "/")[0] == 200
    assert forwarded == []


def test_every_backend_proxy_route_requires_a_session(local_server):
    request, forwarded = local_server
    for path in (
        "/api/system",
        "/api/consultation/example",
        "/api/download-pdf/example",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
    ):
        for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            assert request(method, path, headers={"Authorization": "Bearer " + BACKEND_TOKEN})[0] == 401
    assert forwarded == []


def test_setup_cookie_allows_proxy_and_logout_revokes_it(local_server):
    request, forwarded = local_server
    status, data, headers = request("POST", "/auth/setup", payload=ACCOUNT)
    assert status in (200, 201)
    assert ACCOUNT["password"] not in json.dumps(data)
    assert BACKEND_TOKEN not in json.dumps(data)
    cookie = session_cookie(headers)
    assert cookie["httponly"]
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == 8 * 60 * 60
    authenticated = {"Cookie": f"care_session={cookie.value}"}

    status, data, _ = request("GET", "/auth/session", headers=authenticated)
    assert status == 200
    assert data == {
        "configured": True,
        "authenticated": True,
        "user": {"name": ACCOUNT["name"], "email": ACCOUNT["email"]},
    }
    status, data, _ = request("GET", "/api/system", headers={
        **authenticated, "Authorization": "Bearer attacker", "X-User-Id": "attacker"
    })
    assert status == 200 and data == {"upstream": True}
    assert forwarded[0]["headers"]["Authorization"] == "Bearer " + BACKEND_TOKEN
    assert "Cookie" not in forwarded[0]["headers"]
    assert "X-User-Id" not in forwarded[0]["headers"]

    status, _, headers = request("POST", "/auth/logout", headers=authenticated)
    assert status == 200
    assert session_cookie(headers)["max-age"] == "0"
    assert request("GET", "/api/system", headers=authenticated)[0] == 401
    status, data, _ = request("GET", "/auth/session", headers=authenticated)
    assert status == 200 and data == {"configured": True, "authenticated": False, "user": None}
    assert len(forwarded) == 1


def test_login_recovers_existing_account_and_never_reopens_setup(local_server, auth):
    request, _ = local_server
    auth.setup(ACCOUNT)
    assert request("POST", "/auth/setup", payload=ACCOUNT)[0] == 409
    assert request("POST", "/auth/login", payload={**ACCOUNT, "password": "wrong-password"})[0] == 401
    status, _, headers = request("POST", "/auth/login", payload={
        "email": "  CLINICIAN@EXAMPLE.TEST  ", "password": ACCOUNT["password"]
    })
    assert status == 200
    assert request("GET", "/api/system", headers={
        "Cookie": "care_session=" + session_cookie(headers).value
    })[0] == 200


def test_foreign_host_origin_and_cross_site_requests_cannot_create_an_account(local_server, auth):
    request, forwarded = local_server
    for headers in (
        {"Host": "attacker.example"},
        {"Origin": "https://attacker.example"},
        {"Origin": None},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        assert request("POST", "/auth/setup", payload=ACCOUNT, headers=headers)[0] == 403
    assert not auth.configured
    assert forwarded == []


def test_cross_origin_requests_cannot_use_an_authenticated_proxy(local_server, auth):
    request, forwarded = local_server
    token = auth.setup(ACCOUNT)
    for headers in (
        {"Origin": "https://attacker.example"},
        {"Origin": None},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        assert request("POST", "/api/consultation", payload={}, headers={
            "Cookie": "care_session=" + token, **headers
        })[0] == 403
    assert forwarded == []


def test_auth_rejects_malformed_oversized_and_transfer_encoded_requests(local_server, auth):
    request, _ = local_server
    for body in (b"{invalid", b"[]", b"null"):
        status, _, headers = request("POST", "/auth/setup", body=body, headers={
            "Content-Type": "application/json"
        })
        assert status == 400
        assert headers.get("Connection", "").lower() == "close"
    assert request("POST", "/auth/setup", body=b"x" * (64 * 1024), headers={
        "Content-Type": "application/json"
    })[0] == 413
    assert request("POST", "/auth/setup", payload=ACCOUNT, headers={
        "Transfer-Encoding": "chunked"
    })[0] == 400
    assert request("POST", "/auth/setup", body=json.dumps(ACCOUNT), headers={
        "Content-Type": "text/plain"
    })[0] in (400, 415)
    assert not auth.configured


def test_expired_or_forged_cookie_cannot_download_pdf(local_server, auth, clock):
    request, forwarded = local_server
    token = auth.setup(ACCOUNT)
    clock[0] += 8 * 60 * 60 + 1
    for cookie in (token, "forged-session"):
        assert request("GET", "/api/download-pdf/example", headers={
            "Cookie": "care_session=" + cookie
        })[0] == 401
    assert forwarded == []
