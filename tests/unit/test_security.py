"""Petites fixtures synthétiques ; aucune donnée métier fabriquée."""

import pytest
from cryptography.exceptions import InvalidTag

from rncp_bc3 import security


@pytest.fixture(autouse=True)
def fixed_key(monkeypatch):
    monkeypatch.setattr(security, "key", lambda: b"x" * 32)


def test_encryption_authenticated_context():
    raw = b"ticket fictif de test"
    a = security.encrypt(raw, "id-one")
    b = security.encrypt(raw, "id-one")
    assert a != b and raw not in a
    assert security.decrypt(a, "id-one") == raw
    with pytest.raises(InvalidTag):
        security.decrypt(a, "id-two")
    with pytest.raises(InvalidTag):
        security.decrypt(a[:-1] + bytes([a[-1] ^ 1]), "id-one")


def test_bad_envelope():
    with pytest.raises(ValueError):
        security.decrypt(b"plain", "x")


@pytest.mark.parametrize("value", ["=SUM(1,2)", " +2", "-4", "@cmd", "\t=cmd"])
def test_csv_formula_injection(value):
    assert security.csv_cell(value).startswith("'")


def test_plain_csv():
    assert security.csv_cell("texte normal") == "texte normal"


def test_file_signatures():
    assert security.file_type(b"%PDF-test", "application/pdf") == "application/pdf"
    with pytest.raises(ValueError):
        security.file_type(b"<script>", "application/pdf")
    with pytest.raises(ValueError):
        security.file_type(b"%PDF-test", "text/html")


def test_csrf():
    a = security.csrf_for("opaque-session")
    assert len(a) == 64 and a != security.csrf_for("other-session")
    assert a == security.csrf_for("opaque-session")
