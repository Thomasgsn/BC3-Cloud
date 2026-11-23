"""Cas limites sur vrais services : sessions/logout/brute-force et objet momentanément absent."""

import base64
import json
import os
import secrets
import ssl
import uuid
from pathlib import Path

import httpx
from argon2 import PasswordHasher

from rncp_bc3 import db, storage
from rncp_bc3.config import ROOT, SECRET_DIR
from rncp_bc3.security import token_hash


def test_real_session_logout_expiry_and_login_throttle():
    username = "fixture-auth-" + uuid.uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
            (
                uuid.uuid4(),
                username,
                PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(password),
                "requester",
            ),
        )
    with httpx.Client(
        base_url="https://api:8443",
        verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
        headers={"Origin": os.getenv("BC3_TEST_ORIGIN", "https://localhost:8453")},
        timeout=30,
    ) as client:
        response = client.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        assert client.get("/api/me").status_code == 200
        assert client.post("/api/logout").status_code == 200
        assert client.get("/api/me").status_code == 401
        response = client.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 200
        with db.connect() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at=now()-interval '1 second' WHERE token_hash=%s",
                (token_hash(client.cookies["__Host-bc3"]),),
            )
        assert client.get("/api/me").status_code == 401
        for _ in range(10):
            assert (
                client.post(
                    "/api/login",
                    json={"username": username, "password": "controlled-wrong-fixture"},
                ).status_code
                == 401
            )
        assert (
            client.post("/api/login", json={"username": username, "password": password}).status_code
            == 429
        )
    output = Path(os.getenv("BC3_EVIDENCE_DIR", str(ROOT / "docs/evidence/p1")))
    output.mkdir(parents=True, exist_ok=True)
    (output / "auth-boundaries.json").write_text(
        json.dumps(
            {
                "logout_invalidates_session": True,
                "expired_server_session_rejected": True,
                "ten_failed_attempts_then_429": True,
                "fixture_scope": "Unique synthetic account, no existing user locked",
            },
            indent=2,
        )
        + "\n"
    )


def test_missing_private_object_returns_error_then_recovers():
    # Fixture autonome : aucun objet existant du candidat n’est supprimé.
    username = "fixture-object-" + uuid.uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
            (
                uuid.uuid4(),
                username,
                PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(password),
                "requester",
            ),
        )
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    )
    with httpx.Client(
        base_url="https://api:8443",
        verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
        headers={"Origin": os.getenv("BC3_TEST_ORIGIN", "https://localhost:8453")},
        timeout=30,
    ) as client:
        login = client.post("/api/login", json={"username": username, "password": password})
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        ticket = client.post(
            "/api/tickets",
            json={
                "title": "Fixture objet absent",
                "body": "Cas limite synthétique avec restauration du même contenu.",
            },
        )
        assert ticket.status_code == 201
        response = client.post(
            "/api/tickets/" + ticket.json()["id"] + "/attachments",
            content=png,
            headers={"Content-Type": "image/png"},
        )
        assert response.status_code == 201
        attachment = response.json()
        key = "attachments/" + attachment["id"]
        storage.client().delete_object(Bucket=storage.BUCKET, Key=key)
        try:
            assert client.get("/api/attachments/" + attachment["id"]).status_code == 503
        finally:
            assert storage.put(key, png) == attachment["sha256"]
        assert client.get("/api/attachments/" + attachment["id"]).content == png
    output = Path(os.getenv("BC3_EVIDENCE_DIR", str(ROOT / "docs/evidence/p1")))
    output.mkdir(parents=True, exist_ok=True)
    (output / "missing-object.json").write_text(
        json.dumps(
            {
                "actual_fixture_object_temporarily_removed": True,
                "download_explicit_503": True,
                "fixture_restored_exactly": True,
                "existing_user_objects_touched": False,
            },
            indent=2,
        )
        + "\n"
    )
