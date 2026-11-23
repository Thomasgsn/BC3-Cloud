"""Consommateur dédié : état durable SQL, outbox/reprise et effet idempotent."""

import csv
import io
import json
import logging
import signal
import time
import uuid

from prometheus_client import Counter, Gauge, start_http_server

from . import db, storage
from .security import csv_cell, decrypt

LOG = logging.getLogger("bc3.worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")
JOBS = Counter("bc3_worker_jobs_total", "Exécution des jobs", ["result"])
PENDING = Gauge("bc3_worker_pending", "Jobs en attente")
AGE = Gauge("bc3_worker_oldest_pending_seconds", "Âge du plus ancien job en attente")
STOP = False


def process(job_id):
    i = uuid.UUID(str(job_id))
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM exports WHERE id=%s AND (status='pending' OR (status='processing' AND lease_until<now())) AND attempts<3 FOR UPDATE SKIP LOCKED",
            (i,),
        ).fetchone()
        if not row:
            return False
        c.execute(
            "UPDATE exports SET status='processing',attempts=attempts+1,lease_until=now()+interval '60 seconds',updated_at=now(),error_code=NULL WHERE id=%s",
            (i,),
        )
    try:
        with db.connect() as c:
            user = c.execute(
                "SELECT role FROM users WHERE id=%s", (row["requester_id"],)
            ).fetchone()
            tickets = c.execute(
                "SELECT id,title,body,status,created_at FROM tickets WHERE (%s OR owner_id=%s) ORDER BY created_at LIMIT 5001",
                (user["role"] == "agent", row["requester_id"]),
            ).fetchall()
        if len(tickets) > 5000:
            raise ValueError("Export trop grand pour le profil de démonstration")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["id", "titre", "description", "statut", "créé_le"])
        for t in tickets:
            writer.writerow(
                [
                    str(t["id"]),
                    csv_cell(decrypt(bytes(t["title"]), str(t["id"]) + ":title").decode()),
                    csv_cell(decrypt(bytes(t["body"]), str(t["id"]) + ":body").decode()),
                    t["status"],
                    t["created_at"].isoformat(),
                ]
            )
        key = f"exports/{i}.csv"
        sha = storage.put(key, stream.getvalue().encode("utf-8-sig"))
        with db.connect() as c:
            c.execute(
                "UPDATE exports SET status='complete',object_key=%s,sha256=%s,lease_until=NULL,updated_at=now() WHERE id=%s",
                (key, sha, i),
            )
        JOBS.labels("complete").inc()
        LOG.info(json.dumps({"event": "export_complete", "job_id": str(i), "rows": len(tickets)}))
        return True
    except Exception as e:
        with db.connect() as c:
            c.execute(
                "UPDATE exports SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END,lease_until=NULL,error_code=%s,updated_at=now() WHERE id=%s",
                (type(e).__name__, i),
            )
        JOBS.labels("retry_or_failed").inc()
        raise


def recover():
    with db.connect() as c:
        c.execute(
            "UPDATE exports SET status='failed',error_code='LeaseExpired',updated_at=now() WHERE status='processing' AND lease_until<now() AND attempts>=3"
        )
        rows = c.execute(
            "SELECT id FROM exports WHERE (status='pending' OR (status='processing' AND lease_until<now())) AND attempts<3 AND updated_at<now()-interval '5 seconds' LIMIT 20"
        ).fetchall()
        count = c.execute(
            "SELECT count(*) n,coalesce(extract(epoch from now()-min(created_at)),0) age FROM exports WHERE status IN ('pending','processing')"
        ).fetchone()
    PENDING.set(count["n"])
    AGE.set(float(count["age"]))
    for row in rows:
        storage.enqueue(row["id"])
        with db.connect() as c:
            c.execute("UPDATE exports SET updated_at=now() WHERE id=%s", (row["id"],))


def main():

    def stop(*args):
        global STOP
        STOP = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    start_http_server(9091, certfile="/run/tls/server.crt", keyfile="/run/tls/server.key")
    while not STOP:
        try:
            recover()
            q = storage.client("sqs")
            url = storage.queue_url()
            messages = q.receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
                VisibilityTimeout=60,
            ).get("Messages", [])
            for m in messages:
                try:
                    process(m["Body"])
                except (ValueError, TypeError):
                    storage.deadletter(m["Body"])
                    JOBS.labels("invalid_message").inc()
                else:
                    q.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
                    continue
                q.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        except Exception as e:  # noqa: BLE001 — le daemon journalise et reprend ; SIGTERM reste respecté.
            LOG.warning(json.dumps({"event": "worker_retry", "error_type": type(e).__name__}))
            time.sleep(2)


if __name__ == "__main__":
    main()
