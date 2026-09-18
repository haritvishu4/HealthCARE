"""Loopback-only development server. Keeps the local API token out of browser code."""

import http.client
import json
import os
import sys
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from local_auth import SESSION_SECONDS, AuthError, LocalAuth

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
sys.path.insert(0, str(ROOT / "backend"))


def config():
    result = {}
    for line in (ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    result.update(
        {key: os.environ[key] for key in ("APP_ENV", "DEV_AUTH_TOKEN") if key in os.environ}
    )
    if result.get("APP_ENV") != "development" or len(result.get("DEV_AUTH_TOKEN", "")) < 32:
        raise SystemExit(
            "The local proxy requires APP_ENV=development and a generated DEV_AUTH_TOKEN. Use authenticated HTTPS hosting for production."
        )
    return result


def create_server(settings, auth, port=5173, upstream_port=8000):
    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND), **kwargs)

        def log_message(self, *args):
            pass  # Do not log URLs or submitted patient information.

        def list_directory(self, path):
            self.send_error(404)
            return None

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            super().end_headers()

        def json_response(self, status, payload, token=None, clear_cookie=False):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if token is not None or clear_cookie:
                cookie = SimpleCookie()
                cookie["care_session"] = token or ""
                cookie["care_session"]["path"] = "/"
                cookie["care_session"]["httponly"] = True
                cookie["care_session"]["samesite"] = "Strict"
                cookie["care_session"]["max-age"] = 0 if clear_cookie else SESSION_SECONDS
                self.send_header("Set-Cookie", cookie["care_session"].OutputString())
            if status >= 400:
                # Rejected requests may still have unread bytes in their body.
                self.send_header("Connection", "close")
                self.close_connection = True
            if status == 429:
                self.send_header("Retry-After", "300")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def session_token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            session = cookie.get("care_session")
            return session.value if session else None

        def session_status(self, token=None):
            user = auth.user(token)
            return {"configured": auth.configured, "authenticated": user is not None, "user": user}

        def read_body(self, limit):
            if self.headers.get("Transfer-Encoding"):
                raise AuthError(400, "Use a bounded Content-Length request.")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1:
                raise AuthError(400, "Send only one Content-Length header.")
            try:
                size = int(lengths[0]) if lengths else 0
            except ValueError:
                raise AuthError(400, "Invalid Content-Length.") from None
            if size < 0:
                raise AuthError(400, "Invalid Content-Length.")
            if size > limit:
                raise AuthError(413, "Request is too large.")
            body = self.rfile.read(size) if size else b""
            if len(body) != size:
                raise AuthError(400, "Incomplete request body.")
            return body

        def auth_request(self, path):
            if path == "/auth/session" and self.command in ("GET", "HEAD"):
                self.read_body(0)
                return self.json_response(200, self.session_status(self.session_token()))
            if path not in ("/auth/setup", "/auth/login", "/auth/logout", "/auth/session"):
                raise AuthError(404, "Authentication route not found.")
            if self.command != "POST" or path == "/auth/session":
                raise AuthError(405, "Method not allowed.")
            body = self.read_body(16 * 1024)
            if path == "/auth/logout":
                auth.logout(self.session_token())
                return self.json_response(200, self.session_status(), clear_cookie=True)
            if self.headers.get_content_type() != "application/json":
                raise AuthError(415, "Send account details as JSON.")
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeError):
                raise AuthError(400, "Enter valid account details.") from None
            if not isinstance(payload, dict):
                raise AuthError(400, "Enter valid account details.")
            action = auth.setup if path == "/auth/setup" else auth.login
            token = action(payload, client=self.client_address[0])
            auth.logout(self.session_token())
            return self.json_response(
                201 if path == "/auth/setup" else 200, self.session_status(token), token=token
            )

        def handle_request(self):
            host = self.headers.get("Host", "")
            local_port = self.server.server_port
            if len(self.headers.get_all("Host", [])) != 1 or host not in (
                f"localhost:{local_port}", f"127.0.0.1:{local_port}"
            ):
                return self.send_error(403, "Invalid local host")
            origin = self.headers.get("Origin")
            if len(self.headers.get_all("Origin", [])) > 1 or (
                origin and origin != "http://" + host and not (
                    self.headers.get("Sec-Fetch-Site") == "cross-site"
                    and self.command in ("GET", "HEAD")
                )
            ):
                return self.send_error(403, "Cross-origin request denied")
            if self.command not in ("GET", "HEAD") and not origin:
                return self.send_error(403, "A same-origin request is required")
            try:
                target = urlsplit(self.path)
            except ValueError:
                return self.send_error(400, "Invalid request path")
            if not self.path.startswith("/") or target.scheme or target.netloc or target.fragment:
                return self.send_error(400, "Invalid request path")
            path = target.path
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                # A README link is a legitimate cross-site top-level navigation.
                # Keep rejecting cross-site writes and API calls to preserve CSRF protection.
                if self.command not in ("GET", "HEAD") or path.startswith("/api/"):
                    return self.send_error(403, "Cross-site request denied.")
            try:
                return self.route(path)
            except AuthError as error:
                return self.json_response(error.status, {"detail": error.message})

        def route(self, path):
            if path.startswith("/auth/"):
                return self.auth_request(path)
            if path.startswith("/api/") or path in (
                "/health",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/docs/oauth2-redirect",
            ):
                if auth.user(self.session_token()) is None:
                    raise AuthError(401, "Sign in to continue.")
                return self.proxy()
            resolved = Path(self.translate_path(path)).resolve()
            if not resolved.is_relative_to(FRONTEND) or any(
                part.startswith(".") for part in resolved.relative_to(FRONTEND).parts
            ):
                return self.send_error(404)
            if self.command == "GET":
                self.read_body(0)
                return super().do_GET()
            if self.command == "HEAD":
                self.read_body(0)
                return super().do_HEAD()
            return self.send_error(405)

        def proxy(self):
            body = self.read_body(11 * 1024 * 1024)
            headers = {
                "Authorization": "Bearer " + settings["DEV_AUTH_TOKEN"],
                "Host": f"127.0.0.1:{upstream_port}",
            }
            role = auth.role_for_token(self.session_token())
            if role in {"doctor", "patient"}:
                headers["X-Care-Role"] = role
            for key in ("Content-Type", "Accept"):
                if self.headers.get(key):
                    headers[key] = self.headers[key]
            connection = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=70)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read()
                self.send_response(response.status)
                for key in ("Content-Type", "Content-Disposition", "Retry-After"):
                    if response.getheader(key):
                        self.send_header(key, response.getheader(key))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
            except (OSError, http.client.HTTPException):
                self.json_response(
                    502,
                    {
                        "detail": "Backend unavailable. Start python scripts/run.py and check backend/.env."
                    },
                )
            finally:
                connection.close()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = handle_request

    class ReusableThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    return ReusableThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve():
    from app.config import get_settings
    from app.database import Database

    settings = config()
    database = Database(get_settings())
    server = create_server(
        settings,
        LocalAuth(ROOT / "backend" / ".local-auth.json", database=database),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
