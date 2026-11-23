"""Régression réelle : écriture SQL entre export du snapshot et vrai pg_dump.

Le lanceur pg_dump instrumenté ajoute une ligne de fixture puis exécute le binaire
original ; aucun résultat SQL ou dump n'est simulé. La base restaurée est conservée.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

from rncp_bc3 import db
from rncp_bc3.config import database_ca, secrets, setting


def test_dump_matches_snapshot_with_concurrent_write(monkeypatch, tmp_path):
    module_path = Path("/app/scripts/backup.py")
    spec = importlib.util.spec_from_file_location("snapshot_backup", module_path)
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)
    real_dump = shutil.which("pg_dump")
    assert real_dump
    fixture = "snapshot-regression-" + uuid.uuid4().hex
    launcher = tmp_path / "pg_dump"
    marker = tmp_path / "launcher-executed"
    launcher.write_text(
        "#!" + sys.executable + "\n"
        "import os,sys\nfrom pathlib import Path\nfrom rncp_bc3 import db\n"
        "Path(" + repr(str(marker)) + ").write_text('executed')\n"
        "with db.connect() as conn:\n"
        ' conn.execute("INSERT INTO audit(event) VALUES (%s)", (' + repr(fixture) + ",))\n"
        "os.execv(" + repr(real_dump) + ", [" + repr(real_dump) + "]+sys.argv[1:])\n"
    )
    # /tmp est noexec dans le profil durci : lire le script via Python, sans
    # relâcher le montage. Le résultat renvoyé reste celui du vrai pg_dump.
    real_run = subprocess.run

    def instrumented_run(command, **kwargs):
        if command[0] == "pg_dump":
            command = [sys.executable, str(launcher), *command[1:]]
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", instrumented_run)
    env = os.environ | {
        "PGPASSWORD": secrets()["db_password"],
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": database_ca(),
    }
    host, user, name = (
        setting("DB_HOST", "db"),
        setting("DB_USER", "bc3"),
        setting("DB_NAME", "bc3"),
    )
    raw, counts, tickets = backup.dump_snapshot(host, user, name, env)
    assert marker.exists(), "Le vrai pg_dump doit être précédé du lanceur instrumenté"
    with db.connect() as conn:
        assert (
            conn.execute("SELECT count(*) n FROM audit WHERE event=%s", (fixture,)).fetchone()["n"]
            == 1
        )
        assert conn.execute("SELECT count(*) n FROM audit").fetchone()["n"] > counts["audit"]
    target = "bc3_snapshot_" + uuid.uuid4().hex[:12]
    options = dict(
        host=host,
        user=user,
        password=secrets()["db_password"],
        sslmode="verify-full",
        sslrootcert=database_ca(),
    )
    with psycopg.connect(dbname="postgres", autocommit=True, **options) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
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
        input=raw,
        env=env,
        check=True,
        capture_output=True,
        timeout=90,
    )
    with psycopg.connect(dbname=target, **options) as conn:
        for table, count in counts.items():
            actual = conn.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()[0]
            assert actual == count, table
        assert (
            conn.execute("SELECT count(*) FROM audit WHERE event=%s", (fixture,)).fetchone()[0] == 0
        )
        rows = conn.execute("SELECT id,title,body FROM tickets ORDER BY id").fetchall()
        assert [(r[0], bytes(r[1]), bytes(r[2])) for r in rows] == tickets
    evidence = Path(os.environ.get("BC3_EVIDENCE_DIR", "/app/docs/evidence/followup"))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "backup-snapshot-regression.json").write_text(
        json.dumps(
            {
                "event": "real_backup_snapshot_regression",
                "live_write_after_snapshot": True,
                "write_present_in_active_database": True,
                "write_absent_from_restored_snapshot": True,
                "all_seven_table_counts_match_snapshot": len(counts) == 7,
                "encrypted_ticket_values_exact": True,
                "restored_database_preserved": target,
                "simulation": False,
                "instrumentation": "Launcher inserts one explicitly identified fixture in real SQL, then execs original pg_dump with exported snapshot",
            },
            indent=2,
        )
        + "\n"
    )
