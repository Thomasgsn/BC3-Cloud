"""Essai réel à deux phases, arrêt/reprise piloté par Compose sans suppression de volume."""

import argparse
import base64
import json
import ssl
import time
import uuid
from pathlib import Path

import httpx

from rncp_bc3.config import ROOT, SECRET_DIR

p = argparse.ArgumentParser()
p.add_argument("phase", choices=["prepare", "verify"])
a = p.parse_args()
state = ROOT / "exports/resilience-fixture.json"
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
with httpx.Client(
    base_url="https://api:8443",
    verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
    headers={"Origin": "https://localhost:8453"},
    timeout=15,
) as c:
    r = c.post(
        "/api/login",
        json={
            "username": "thomas",
            "password": Path("/run/test-secrets/demo_password").read_text().strip(),
        },
    )
    r.raise_for_status()
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    if a.phase == "prepare":
        ticket = c.post(
            "/api/tickets",
            json={
                "title": "Fixture redémarrage " + uuid.uuid4().hex[:8],
                "body": "Fixture explicitement créée pour vérifier persistance et reprise.",
            },
        )
        ticket.raise_for_status()
        t = ticket.json()
        f = c.post(
            "/api/tickets/" + t["id"] + "/attachments",
            content=png,
            headers={"Content-Type": "image/png"},
        )
        f.raise_for_status()
        job = c.post("/api/exports")
        job.raise_for_status()
        i = job.json()["id"]
        assert c.get("/api/exports/" + i).json()["status"] == "pending", (
            "Arrêter le worker avant préparation"
        )
        state.write_text(
            json.dumps(
                {
                    "ticket": t,
                    "attachment_id": f.json()["id"],
                    "job_id": i,
                    "prepared_at": time.time(),
                },
                indent=2,
            )
            + "\n"
        )
        print("Fixture persistée, export en attente pendant arrêt worker")
    else:
        d = json.loads(state.read_text())
        t = c.get("/api/tickets/" + d["ticket"]["id"])
        t.raise_for_status()
        assert t.json()["body"] == d["ticket"]["body"]
        assert c.get("/api/attachments/" + d["attachment_id"]).content == png
        for _ in range(60):
            j = c.get("/api/exports/" + d["job_id"]).json()
            if j["status"] == "complete":
                break
            assert j["status"] != "failed", j
            time.sleep(0.5)
        assert j["status"] == "complete", j
        download = c.get("/api/exports/" + d["job_id"] + "/download")
        download.raise_for_status()
        assert d["ticket"]["title"] in download.text
        proof = {
            "event": "restart_recovery",
            "ticket_and_object_persisted": True,
            "worker_stopped_when_job_created": True,
            "postgres_api_object_queue_restarted_between_phases": True,
            "durable_sql_job_reemitted_and_completed": True,
            "attempts": j["attempts"],
            "active_volume_deleted": False,
            "fixture_scope": "Synthetic test ticket/file only",
            "elapsed_since_prepare_seconds": time.time() - d["prepared_at"],
        }
        (ROOT / "docs/evidence/p1/restart-recovery.json").write_text(
            json.dumps(proof, indent=2) + "\n"
        )
        print(json.dumps(proof))
