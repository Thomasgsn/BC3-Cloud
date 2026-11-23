"""Charge réelle sur 200 tickets de fixture, sans données de vrais clients."""

import concurrent.futures
import json
import os
import secrets
import ssl
import threading
import time
import uuid
from pathlib import Path

import httpx
from argon2 import PasswordHasher

from rncp_bc3 import db
from rncp_bc3.config import SECRET_DIR
from rncp_bc3.security import encrypt

username = "fixture-load-" + uuid.uuid4().hex[:10]
password = secrets.token_urlsafe(24)
owner = uuid.uuid4()
with db.connect() as c:
    c.execute(
        "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
        (owner, username, PasswordHasher().hash(password), "requester"),
    )
    for n in range(200):
        i = uuid.uuid4()
        c.execute(
            "INSERT INTO tickets(id,owner_id,title,body) VALUES (%s,%s,%s,%s)",
            (
                i,
                owner,
                encrypt(("Fixture charge " + str(n)).encode(), str(i) + ":title"),
                encrypt(
                    b"Observation synthetique reservee au test de charge du BC3.",
                    str(i) + ":body",
                ),
            ),
        )
client = httpx.Client(
    base_url="https://api:8443",
    verify=ssl.create_default_context(cafile=str(SECRET_DIR / "ca.crt")),
    headers={"Origin": "https://bc3.local:8455"},
    timeout=5,
)
r = client.post("/api/login", json={"username": username, "password": password})
r.raise_for_status()
duration = int(os.getenv("BC3_LOAD_SECONDS", "240"))
start = time.monotonic()
deadline = start + duration
lock = threading.Lock()
latencies = []
statuses = {}
invalid = 0


def load():
    global invalid
    while time.monotonic() < deadline:
        began = time.monotonic()
        try:
            response = client.get("/api/tickets")
            status = str(response.status_code)
            valid = response.status_code == 200 and len(response.json()) == 200
        except httpx.HTTPError:
            status = "transport_error"
            valid = False
        with lock:
            latencies.append(time.monotonic() - began)
            statuses[status] = statuses.get(status, 0) + 1
            if not valid:
                invalid += 1
        time.sleep(0.15)


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(load) for _ in range(4)]
    while not all(f.done() for f in futures):
        time.sleep(10)
        print(
            json.dumps(
                {
                    "event": "load_progress",
                    "requests": len(latencies),
                    "seconds": time.monotonic() - start,
                }
            ),
            flush=True,
        )
    for f in futures:
        f.result()
client.close()
ordered = sorted(latencies)
report = {
    "event": "real_api_load",
    "seconds": time.monotonic() - start,
    "concurrency": 4,
    "pause_per_thread_seconds": 0.15,
    "fixture_rows_per_response": 200,
    "requests": len(latencies),
    "status_counts": statuses,
    "invalid_or_failed_responses": invalid,
    "availability_fraction": 1 - invalid / max(1, len(latencies)),
    "latency_p95_seconds": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
    "latency_max_seconds": max(ordered),
    "tls_verified": True,
    "fixture_scope": "Synthetic test accounts/tickets only, actual API/SQL and encryption; no mock service",
}
Path("/tmp/load-result.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)
