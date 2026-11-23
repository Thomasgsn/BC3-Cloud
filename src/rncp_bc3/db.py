"""PostgreSQL : schéma versionné, transactions courtes et TLS vérifié."""

import hashlib
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import database_ca, secrets, setting

SCHEMA = """
CREATE TABLE users(id uuid PRIMARY KEY, username text NOT NULL UNIQUE, password_hash text NOT NULL, role text NOT NULL CHECK(role IN ('requester','agent')), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE sessions(token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id), expires_at timestamptz NOT NULL);
CREATE TABLE tickets(id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id), assignee_id uuid REFERENCES users(id), title bytea NOT NULL, body bytea NOT NULL, status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','closed')), version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE attachments(id uuid PRIMARY KEY,ticket_id uuid NOT NULL REFERENCES tickets(id),object_key text NOT NULL UNIQUE,mime text NOT NULL,size integer NOT NULL,sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE exports(id uuid PRIMARY KEY,requester_id uuid NOT NULL REFERENCES users(id),status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','complete','failed')),object_key text,sha256 text,attempts integer NOT NULL DEFAULT 0,lease_until timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),error_code text);
CREATE TABLE audit(id bigserial PRIMARY KEY,event text NOT NULL,actor text,at timestamptz NOT NULL DEFAULT now());
CREATE INDEX tickets_owner ON tickets(owner_id);CREATE INDEX jobs_pending ON exports(status,lease_until);CREATE INDEX audit_time ON audit(event,at);
"""


@contextmanager
def connect():
    with psycopg.connect(
        host=setting("DB_HOST", "db"),
        dbname=setting("DB_NAME", "bc3"),
        user=setting("DB_USER", "bc3"),
        password=secrets()["db_password"],
        port=int(setting("DB_PORT", "5432")),
        sslmode="verify-full",
        sslrootcert=database_ca(),
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        yield conn


def migrate():
    sha = hashlib.sha256(SCHEMA.encode()).hexdigest()
    with connect() as c:
        c.execute("SELECT pg_advisory_xact_lock(4087503)")
        present = c.execute("SELECT to_regclass('public.schema_migrations') present").fetchone()[
            "present"
        ]
        if present:
            row = c.execute("SELECT sha256 FROM schema_migrations WHERE version=1").fetchone()
            if not row or row["sha256"] != sha:
                raise RuntimeError("Migration absente ou modifiée")
            return
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())"
        )
        row = c.execute("SELECT sha256 FROM schema_migrations WHERE version=1").fetchone()
        if row and row["sha256"] != sha:
            raise RuntimeError("Migration déjà appliquée avec une autre empreinte")
        if not row:
            c.execute(SCHEMA)
            c.execute("INSERT INTO schema_migrations(version,sha256) VALUES (1,%s)", (sha,))


def audit(event, actor=None):
    with connect() as c:
        c.execute("INSERT INTO audit(event,actor) VALUES (%s,%s)", (event, actor))
