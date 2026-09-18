import json

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import Audit


class Database:
    def __init__(self, settings):
        kwargs = (
            {"connect_args": {"check_same_thread": False, "timeout": 20}}
            if settings.database_url.startswith("sqlite")
            else {}
        )
        self.engine = create_engine(settings.database_url, pool_pre_ping=True, **kwargs)
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def sqlite_connect(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.cipher = Fernet(settings.field_encryption_key.encode())

    def seal(self, data):
        return self.cipher.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def open(self, data):
        return json.loads(self.cipher.decrypt(data))

    def audit(self, session, actor_id, action, resource_id):
        session.add(Audit(actor_id=actor_id, action=action, resource_id=resource_id))
