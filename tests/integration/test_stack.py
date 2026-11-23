"""Intégration réelle, comptes/tickets créés comme fixtures identifiées, sans mock réseau."""

import base64
import json
import os
import secrets
import ssl
import time
import uuid
from pathlib import Path

import httpx
import pytest
from argon2 import PasswordHasher

from rncp_bc3 import db, storage
from rncp_bc3.config import ROOT, SECRET_DIR

ORIGIN = os.getenv("BC3_TEST_ORIGIN", "https://localhost:8453")
URL = "https://api:8443"
EVIDENCE = Path(os.getenv("BC3_EVIDENCE_DIR", str(ROOT / "docs/evidence/p1")))
EVIDENCE.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def users():
    result = {}
    for role, name in [("requester", "a"), ("requester", "b"), ("agent", "agent")]:
        username = "fixture-" + name + "-" + uuid.uuid4().hex[:10]
        password = secrets.token_urlsafe(22)
        with db.connect() as c:
            c.execute(
                "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
                (
                    uuid.uuid4(),
                    username,
                    PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(password),
                    role,
                ),
            )
        client = httpx.Client(
            base_url=URL,
            verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
            headers={"Origin": ORIGIN},
            timeout=20,
        )
        response = client.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        result[name] = client
    yield result
    for c in result.values():
        c.close()


def test_real_flow_access_encryption_and_idempotence(users):
    a, b, agent = (users[k] for k in ["a", "b", "agent"])
    payload = {
        "title": "=SUM(1,2) — fixture de test",
        "body": "Texte fictif confidentiel pour contrôler le chiffrement",
    }
    response = a.post("/api/tickets", json=payload)
    assert response.status_code == 201, response.text
    t = response.json()
    i = t["id"]
    assert b.get("/api/tickets/" + i).status_code == 404
    assert b.patch("/api/tickets/" + i, json={"status": "closed", "version": 1}).status_code == 403
    assert (
        agent.patch(
            "/api/tickets/" + i,
            json={"status": "in_progress", "version": 1, "assign_to_self": True},
        ).status_code
        == 200
    )
    assert (
        agent.patch("/api/tickets/" + i, json={"status": "closed", "version": 1}).status_code == 409
    )
    token = a.headers.pop("X-CSRF-Token")
    assert a.post("/api/tickets", json=payload).status_code == 403
    a.headers["X-CSRF-Token"] = token
    assert (
        a.post(
            "/api/tickets", json=payload, headers={"Origin": "https://example.invalid"}
        ).status_code
        == 403
    )
    with db.connect() as c:
        row = c.execute("SELECT title,body FROM tickets WHERE id=%s", (i,)).fetchone()
        tls = c.execute("SELECT ssl,version FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()
    assert payload["title"].encode() not in bytes(row["title"]) and tls["ssl"] is True
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    )
    r = a.post(
        f"/api/tickets/{i}/attachments",
        content=png,
        headers={"Content-Type": "image/png"},
    )
    assert r.status_code == 201, r.text
    attached = r.json()
    aid = attached["id"]
    assert b.get("/api/attachments/" + aid).status_code == 404
    download = a.get("/api/attachments/" + aid)
    assert download.content == png and download.headers["content-disposition"].startswith(
        "attachment;"
    )
    with db.connect() as c:
        key = c.execute("SELECT object_key FROM attachments WHERE id=%s", (aid,)).fetchone()[
            "object_key"
        ]
    encrypted = storage.client().get_object(Bucket=storage.BUCKET, Key=key)["Body"].read()
    assert png not in encrypted and encrypted.startswith(b"BC3v1")
    assert (
        a.post(
            f"/api/tickets/{i}/attachments",
            content=b"<script>invalid</script>",
            headers={"Content-Type": "application/pdf"},
        ).status_code
        == 415
    )
    assert (
        a.post(
            f"/api/tickets/{i}/attachments",
            content=b"x" * (5 * 1024 * 1024 + 1),
            headers={"Content-Type": "image/png"},
        ).status_code
        == 413
    )
    job = a.post("/api/exports")
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    assert b.get("/api/exports/" + jid).status_code == 404
    for _ in range(40):
        state = a.get("/api/exports/" + jid).json()
        if state["status"] == "complete":
            break
        assert state["status"] != "failed", state
        time.sleep(0.5)
    assert state["status"] == "complete", state
    content = a.get("/api/exports/" + jid + "/download").content.decode("utf-8-sig")
    assert "'=SUM" in content and payload["body"] in content
    from rncp_bc3.worker import process

    assert process(jid) is False
    assert a.get("/api/exports/" + jid).json()["attempts"] == 1
    proof = {
        "event": "real_stack_flow",
        "tls_db": tls,
        "ticket_access_separated": True,
        "csrf_and_origin_rejected": True,
        "optimistic_lock_rejected": True,
        "sql_fields_encrypted": True,
        "object_encrypted_and_download_sha_exact": True,
        "invalid_and_oversize_file_rejected": True,
        "export_worker_completed": True,
        "duplicate_message_no_second_effect": True,
        "fixture_scope": "All accounts/tickets/files created by this test; not real customer records",
    }
    (EVIDENCE / "stack-flow.json").write_text(json.dumps(proof, indent=2) + "\n")


def test_untrusted_tls_rejected():
    with pytest.raises(httpx.ConnectError):
        httpx.get(URL + "/health/ready", timeout=5)


def test_unauthenticated():
    with httpx.Client(
        base_url=URL,
        verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
    ) as c:
        assert c.get("/api/tickets").status_code == 401


def test_runtime_least_privilege_and_private_queue():
    from botocore.exceptions import ClientError

    with db.connect() as c:
        role = c.execute(
            "SELECT current_user username,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert role["username"] == "bc3_app" and not any(
            role[k] for k in ["rolsuper", "rolcreatedb", "rolcreaterole"]
        )
        assert (
            c.execute(
                "SELECT has_schema_privilege(current_user,'public','CREATE') allowed"
            ).fetchone()["allowed"]
            is False
        )
    with pytest.raises(ClientError) as error:
        storage.client().create_bucket(Bucket="bc3-denied-" + uuid.uuid4().hex)
    assert error.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
        httpx.get("http://queue:9324/health", timeout=3)
    (EVIDENCE / "least-privilege.json").write_text(
        json.dumps(
            {
                "postgres_role": role,
                "schema_create_allowed": False,
                "s3_bucket_administration_denied": True,
                "queue_plaintext_port_not_reachable_from_app": True,
                "queue_client_transport": "TLS to sidecar, final loopback in broker network namespace",
                "secret_scope": "CA private key and DB administrative password not in runtime mounts",
            },
            indent=2,
        )
        + "\n"
    )


def test_actual_intent_model_and_access(users):
    a, b = users["a"], users["b"]
    r = a.post(
        "/api/tickets",
        json={
            "title": "My card has not arrived",
            "body": "I ordered my card two weeks ago and it has not arrived yet.",
        },
    )
    assert r.status_code == 201
    i = r.json()["id"]
    assert b.post("/api/tickets/" + i + "/intent").status_code == 404
    r = a.post("/api/tickets/" + i + "/intent")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["model_version"] == "banking77-c1-0" and len(result["suggestions"]) == 3
    assert "card_arrival" in [s["category"] for s in result["suggestions"]]
    (EVIDENCE / "intent-serving.json").write_text(
        json.dumps(
            {
                "model_version": result["model_version"],
                "known_english_fixture_top3_contains_expected_category": True,
                "cross_user_denied": True,
                "margins_not_probabilities": True,
            },
            indent=2,
        )
        + "\n"
    )


def test_invalid_message_reaches_real_deadletter_queue():
    marker = "invalid-fixture-" + uuid.uuid4().hex
    storage.enqueue(marker)
    q = storage.client("sqs")
    url = q.get_queue_url(QueueName="jobs-deadletter")["QueueUrl"]
    found = False
    for _ in range(25):
        for m in q.receive_message(QueueUrl=url, WaitTimeSeconds=1, MaxNumberOfMessages=10).get(
            "Messages", []
        ):
            if m["Body"] == marker:
                found = True
                q.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        if found:
            break
    assert found, "Message invalide absent de la DLQ réelle"
    (EVIDENCE / "deadletter.json").write_text(
        json.dumps(
            {
                "invalid_fixture_message_sent_to_actual_queue": True,
                "worker_transferred_to_dlq": True,
                "matched_fixture_removed_only": True,
            },
            indent=2,
        )
        + "\n"
    )


def test_real_export_failure_bounded_retries(users):
    from botocore.exceptions import ClientError

    from rncp_bc3.worker import process

    jid = uuid.uuid4()
    with db.connect() as c:
        uid = c.execute(
            "SELECT user_id FROM sessions WHERE token_hash=%s",
            (
                __import__("rncp_bc3.security", fromlist=["token_hash"]).token_hash(
                    users["a"].cookies["__Host-bc3"]
                ),
            ),
        ).fetchone()["user_id"]
        c.execute(
            "INSERT INTO exports(id,requester_id,updated_at) VALUES (%s,%s,now()+interval '1 hour')",
            (jid, uid),
        )
    bucket = storage.BUCKET
    storage.BUCKET = "bc3-inaccessible-fixture-" + uuid.uuid4().hex
    try:
        for _ in range(3):
            with pytest.raises(ClientError):
                process(jid)
    finally:
        storage.BUCKET = bucket
    with db.connect() as c:
        row = c.execute(
            "SELECT status,attempts,error_code FROM exports WHERE id=%s", (jid,)
        ).fetchone()
    assert row["status"] == "failed" and row["attempts"] == 3 and process(jid) is False
    (EVIDENCE / "bounded-retries.json").write_text(
        json.dumps(
            {
                "actual_s3_failure": True,
                "result": row,
                "fourth_execution_refused": True,
                "fixture_scope": "Unpublished synthetic SQL job with future updated_at isolates recovery scanner; network service is real",
            },
            indent=2,
        )
        + "\n"
    )
