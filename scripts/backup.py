"""Sauvegarde réelle chiffrée S3 et restauration vers une base neuve uniquement."""

import argparse
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime

import psycopg
from psycopg import sql

from rncp_bc3 import db, storage
from rncp_bc3.config import ROOT, database_ca, secrets, setting

TABLES = ("users", "sessions", "tickets", "attachments", "exports", "audit", "schema_migrations")


def dump_snapshot(host, user, name, env):
    """Le dump et ses témoins lisent le même snapshot malgré les écritures concurrentes."""
    with db.connect() as original:
        original.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        snapshot = original.execute("SELECT pg_export_snapshot() snapshot").fetchone()["snapshot"]
        counts = {
            table: original.execute(
                sql.SQL("SELECT count(*) n FROM {}").format(sql.Identifier(table))
            ).fetchone()["n"]
            for table in TABLES
        }
        rows = original.execute("SELECT id,title,body FROM tickets ORDER BY id").fetchall()
        tickets = [(row["id"], bytes(row["title"]), bytes(row["body"])) for row in rows]
        raw = subprocess.run(
            [
                "pg_dump",
                "-h",
                host,
                "-U",
                user,
                "-d",
                name,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--snapshot",
                snapshot,
            ],
            env=env,
            check=True,
            capture_output=True,
            timeout=90,
        ).stdout
    return raw, counts, tickets


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verify-restore", action="store_true")
    a = p.parse_args()
    env = os.environ | {
        "PGPASSWORD": secrets()["db_password"],
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": database_ca(),
    }
    host = setting("DB_HOST", "db")
    user = setting("DB_USER", "bc3")
    name = setting("DB_NAME", "bc3")
    raw, expected_counts, expected_tickets = dump_snapshot(host, user, name, env)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("Sauvegarde hors budget local")
    identifier = uuid.uuid4().hex
    key = "backups/" + identifier + ".dump"
    sha = storage.put(key, raw)
    restored = storage.get(key, sha)
    assert restored == raw
    result = {
        "at_utc": datetime.now(UTC).isoformat(),
        "event": "encrypted_backup",
        "sha256": sha,
        "bytes": len(raw),
        "object_key": key,
        "download_exact": True,
        "restoration": None,
        "source_consistency": "Shared exported PostgreSQL REPEATABLE READ snapshot for dump, table counts and encrypted ticket values",
        "scope": "Real local PostgreSQL and S3, no cloud execution",
    }
    if a.verify_restore:
        target = "bc3_restore_" + identifier[:12]
        with psycopg.connect(
            host=host,
            dbname="postgres",
            user=user,
            password=secrets()["db_password"],
            sslmode="verify-full",
            sslrootcert=database_ca(),
            autocommit=True,
        ) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        subprocess.run(
            [
                "pg_restore",
                "-h",
                host,
                "-U",
                user,
                "-d",
                target,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
            ],
            input=restored,
            env=env,
            check=True,
            capture_output=True,
        )
        counts = {}
        with psycopg.connect(
            host=host,
            dbname=target,
            user=user,
            password=secrets()["db_password"],
            sslmode="verify-full",
            sslrootcert=database_ca(),
        ) as copy:
            for table in TABLES:
                n = expected_counts[table]
                other = copy.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()[0]
                assert n == other, (table, n, other)
                counts[table] = n
            b1 = copy.execute("SELECT id,title,body FROM tickets ORDER BY id").fetchall()
            assert expected_tickets == [(r[0], bytes(r[1]), bytes(r[2])) for r in b1]
        result["restoration"] = {
            "target": target,
            "table_counts": counts,
            "encrypted_ticket_values_exact": True,
            "active_database_overwritten": False,
            "target_preserved_no_drop": True,
        }
    (ROOT / "docs/evidence/p1").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/evidence/p1/backup-restore.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
