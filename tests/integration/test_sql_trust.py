"""Vraie connexion SQL : CA séparée respectée, aucun fallback de confiance."""

import ssl

import psycopg
import pytest

from rncp_bc3 import config, db


def test_explicit_sql_trust_and_unknown_ca_refused(monkeypatch, tmp_path):
    alternate = tmp_path / "database-ca.crt"
    alternate.write_bytes((config.SECRET_DIR / "ca.crt").read_bytes())
    monkeypatch.setenv("DB_SSLROOTCERT", str(alternate))
    with db.connect() as conn:
        assert conn.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[
            "ssl"
        ]
    monkeypatch.setenv("DB_SSLROOTCERT", ssl.get_default_verify_paths().cafile)
    with pytest.raises(psycopg.OperationalError):
        with db.connect():
            pytest.fail("La CA du laboratoire ne figure pas dans le magasin public")
    monkeypatch.setenv("DB_SSLROOTCERT", str(tmp_path / "missing.crt"))
    with pytest.raises(psycopg.OperationalError):
        with db.connect():
            pytest.fail("Une CA absente ne doit pas déclencher de fallback")
