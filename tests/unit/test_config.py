"""Les paramètres cloud ne relâchent ni les hôtes ni la vérification SQL."""

import pytest

from rncp_bc3 import config


def test_default_and_separate_database_ca(monkeypatch):
    monkeypatch.delenv("DB_SSLROOTCERT", raising=False)
    assert config.database_ca() == str(config.SECRET_DIR / "ca.crt")
    monkeypatch.setenv("DB_SSLROOTCERT", "/run/rds/rds-ca.crt")
    assert config.database_ca() == "/run/rds/rds-ca.crt"


def test_explicit_public_host(monkeypatch):
    monkeypatch.setenv("BC3_PUBLIC_HOST", "support.example.org")
    assert config.public_host() == "support.example.org"


@pytest.mark.parametrize(
    "host",
    [
        "*",
        "*.example.org",
        "https://example.org",
        "example.org:443",
        "-bad.example",
        "bad..example",
        "example.org,evil.org",
    ],
)
def test_reject_ambiguous_public_host(monkeypatch, host):
    monkeypatch.setenv("BC3_PUBLIC_HOST", host)
    with pytest.raises(ValueError):
        config.public_host()
