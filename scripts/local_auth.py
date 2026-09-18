"""Single-workspace login for the loopback-only development server."""

import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy import select

SESSION_SECONDS = 8 * 60 * 60
VALID_ROLES = {"doctor", "patient"}


class AuthError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def password_hash(password, salt):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt), n=2**17, r=8, p=1,
        maxmem=256 * 1024 * 1024, dklen=32,
    ).hex()


class LocalAuth:
    def __init__(self, path=None, clock=time.time, database=None):
        self.path = Path(path)
        self.database = database
        self.clock = clock
        self.lock = threading.RLock()
        self.sessions = {}
        self.roles = {}
        self.identities = {}
        self.attempts = {}
        self.account = self._read_account()

    def _read_account(self):
        if self.database is not None:
            from app.models import WorkspaceAccount

            with self.database.sessions.begin() as session:
                account = session.get(WorkspaceAccount, "workspace")
                if account is None:
                    legacy = self._read_file_account()
                    if legacy is None:
                        return None
                    account = WorkspaceAccount(
                        id="workspace",
                        **{key: legacy[key] for key in (
                            "name", "email", "algorithm", "salt", "password_hash"
                        )},
                        role=legacy.get("role", "patient"),
                    )
                    session.add(account)
                return {
                    "version": 1,
                    "name": account.name,
                    "email": account.email,
                    "role": account.role if account.role in VALID_ROLES else "patient",
                    "algorithm": account.algorithm,
                    "salt": account.salt,
                    "password_hash": account.password_hash,
                }
        return self._read_file_account()

    def _read_file_account(self):
        try:
            with self.path.open(encoding="utf-8") as stream:
                account = json.load(stream)
            role = account.get("role", "patient")
            if role not in VALID_ROLES:
                raise ValueError("Invalid account")
            if (
                account.get("version") != 1
                or account.get("algorithm") != "scrypt-131072-8-1"
                or not isinstance(account.get("email"), str)
                or not isinstance(account.get("name"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", account.get("salt", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", account.get("password_hash", ""))
            ):
                raise ValueError("Invalid account")
            account["role"] = role
            return account
        except FileNotFoundError:
            return None
        except (OSError, ValueError, AttributeError, TypeError):
            raise RuntimeError(
                "The local login file cannot be read. Restore backend/.local-auth.json "
                "from your backup; existing patient records have not been changed."
            ) from None

    @property
    def configured(self):
        return self.account is not None

    def _account_for_role(self, role, fallback=True):
        if self.database is None:
            return self.account if fallback and self.account and self.account.get("role") == role else None
        from app.models import WorkspaceAccount

        with self.database.sessions.begin() as session:
            account = session.scalar(
                select(WorkspaceAccount).where(WorkspaceAccount.role == role).order_by(WorkspaceAccount.created_at)
            )
            if account is None and fallback:
                return self.account
            if account is None:
                return None
            return {
                "version": 1,
                "name": account.name,
                "email": account.email,
                "role": account.role if account.role in VALID_ROLES else "patient",
                "algorithm": account.algorithm,
                "salt": account.salt,
                "password_hash": account.password_hash,
            }

    def _account_for_email(self, email):
        if self.database is None:
            return self.account
        from app.models import WorkspaceAccount

        with self.database.sessions.begin() as session:
            account = session.scalar(
                select(WorkspaceAccount).where(WorkspaceAccount.email == email)
            )
            if account is None:
                return None
            return {
                "version": 1,
                "name": account.name,
                "email": account.email,
                "role": account.role if account.role in VALID_ROLES else "patient",
                "algorithm": account.algorithm,
                "salt": account.salt,
                "password_hash": account.password_hash,
            }

    def _credentials(self, data, setup=False):
        if not isinstance(data, dict):
            raise AuthError(400, "Enter your email and password.")
        email, password = data.get("email"), data.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            raise AuthError(400, "Enter your email and password.")
        email = email.strip().casefold()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise AuthError(400, "Enter a valid email address.")
        if not 1 <= len(password) <= 128:
            raise AuthError(400, "Enter a password of no more than 128 characters.")
        if setup and len(password) < 12:
            raise AuthError(400, "Use at least 12 characters for your password.")
        try:
            email.encode("utf-8")
            password.encode("utf-8")
        except UnicodeError:
            raise AuthError(400, "Enter a valid email and password.") from None
        return email, password

    def _role(self, data, *, setup=False):
        role = data.get("role", "patient") if isinstance(data, dict) else "patient"
        if role not in VALID_ROLES:
            raise AuthError(400, "Choose a valid workspace role.")
        return role

    def _attempt(self, client):
        now = self.clock()
        self.attempts = {key: value for key, value in self.attempts.items() if value[1] > now}
        count, expires = self.attempts.get(client, (0, now + 300))
        if count >= 5:
            raise AuthError(429, "Too many sign-in attempts. Try again in 5 minutes.")
        self.attempts[client] = (count + 1, expires)

    def _new_session(self, role="patient"):
        now = self.clock()
        self.sessions = {key: expires for key, expires in self.sessions.items() if expires > now}
        # Keep bounded state even if an authenticated local client repeatedly signs in.
        if len(self.sessions) >= 20:
            self.sessions.pop(min(self.sessions, key=self.sessions.get))
        token = secrets.token_urlsafe(32)
        key = hashlib.sha256(token.encode()).hexdigest()
        self.sessions[key] = now + SESSION_SECONDS
        self.roles[key] = role if role in VALID_ROLES else "patient"
        self.identities[key] = self._account_for_role(self.roles[key])
        return token

    def setup(self, data, client="local"):
        with self.lock:
            role = self._role(data, setup=True)
            existing = self._account_for_role(role, fallback=False) if self.configured else None
            if existing is not None:
                raise AuthError(409, "This workspace already has a %s account. Sign in instead." % role)
            self._attempt(client)
            email, password = self._credentials(data, setup=True)
            name = data.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                raise AuthError(400, "Enter your name (up to 100 characters).")
            salt = secrets.token_hex(16)
            account = {
                "version": 1, "name": name.strip(), "email": email, "role": role,
                "algorithm": "scrypt-131072-8-1", "salt": salt,
                "password_hash": password_hash(password, salt),
            }
            if self.database is not None:
                from sqlalchemy.exc import IntegrityError
                from app.models import WorkspaceAccount

                try:
                    with self.database.sessions.begin() as session:
                        account_id = "workspace" if not self.configured else "workspace-%s" % role
                        session.add(WorkspaceAccount(id=account_id, **{
                            key: account[key] for key in (
                                "name", "email", "role", "algorithm", "salt", "password_hash"
                            )
                        }))
                except IntegrityError:
                    self.account = self._read_account()
                    raise AuthError(409, "This workspace already has an account. Sign in instead.") from None
                self.account = account
                self.attempts.pop(client, None)
                return self._new_session(role)
            temporary = None
            try:
                # Publish a complete file without replacing any existing account.
                # Another process must never observe a half-written password hash.
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent,
                    prefix=".local-auth-", delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    json.dump(account, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, self.path)
            except FileExistsError:
                self.account = self._read_account()
                raise AuthError(409, "This workspace already has an account. Sign in instead.") from None
            except OSError:
                raise AuthError(503, "Could not save your account. Check local folder permissions.") from None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self.account = account
            self.attempts.pop(client, None)
            return self._new_session(role)

    def login(self, data, client="local"):
        with self.lock:
            self._attempt(client)
            email, password = self._credentials(data)
            role = self._role(data)
            if not self.configured:
                raise AuthError(409, "Set up your workspace account first.")
            account = self._account_for_email(email)
            if account is None:
                raise AuthError(401, "Email or password is incorrect.")
            candidate = password_hash(password, account["salt"])
            password_matches = secrets.compare_digest(candidate, account["password_hash"])
            email_matches = secrets.compare_digest(email.encode(), account["email"].encode())
            if not (password_matches and email_matches):
                raise AuthError(401, "Email or password is incorrect.")
            if account.get("role") != role:
                raise AuthError(403, "Choose the role registered for this account.")
            self.attempts.pop(client, None)
            return self._new_session(role)

    def user(self, token):
        if not token or not isinstance(token, str) or len(token) > 128:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            if not self.configured or self.sessions.get(key, 0) <= self.clock():
                self.sessions.pop(key, None)
                self.roles.pop(key, None)
                self.identities.pop(key, None)
                return None
            account = self.identities.get(key) or self.account
            return {"name": account["name"], "email": account["email"]}

    def role_for_token(self, token):
        if not token or not isinstance(token, str) or len(token) > 128:
            return "patient"
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            if not self.configured or self.sessions.get(key, 0) <= self.clock():
                self.sessions.pop(key, None)
                self.roles.pop(key, None)
                self.identities.pop(key, None)
                return "patient"
            role = self.roles.get(key, self.account.get("role", "patient"))
            return role if role in VALID_ROLES else "patient"

    def logout(self, token):
        if isinstance(token, str) and len(token) <= 128:
            with self.lock:
                key = hashlib.sha256(token.encode()).hexdigest()
                self.sessions.pop(key, None)
                self.roles.pop(key, None)
                self.identities.pop(key, None)
