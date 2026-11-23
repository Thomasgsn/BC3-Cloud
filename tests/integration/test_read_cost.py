"""Régression de coût réelle : lecture de clé constante sur une réponse de 200 tickets."""

import uuid

from argon2 import PasswordHasher

from rncp_bc3 import db, security
from rncp_bc3.api import tickets


def test_listing_reads_encryption_configuration_once(monkeypatch):
    owner = uuid.uuid4()
    with db.connect() as conn:
        user = conn.execute(
            "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s) RETURNING *",
            (
                owner,
                "fixture-read-cost-" + uuid.uuid4().hex[:10],
                PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(
                    uuid.uuid4().hex
                ),
                "requester",
            ),
        ).fetchone()
        for index in range(200):
            identifier = uuid.uuid4()
            conn.execute(
                "INSERT INTO tickets(id,owner_id,title,body) VALUES (%s,%s,%s,%s)",
                (
                    identifier,
                    owner,
                    security.encrypt(
                        ("Fixture coût " + str(index)).encode(), str(identifier) + ":title"
                    ),
                    security.encrypt(
                        b"Synthetic performance regression fixture", str(identifier) + ":body"
                    ),
                ),
            )
    original = security.configuration
    calls = 0

    def measured_configuration():
        nonlocal calls
        calls += 1
        return (
            original()
        )  # Instrumentation seulement, vraie lecture du secret, aucune substitution.

    monkeypatch.setattr(security, "configuration", measured_configuration)
    result = tickets(user=user)
    assert len(result) == 200 and result[0]["body"] == "Synthetic performance regression fixture"
    assert calls == 1, f"La réponse de 200 tickets lit la configuration {calls} fois au lieu de 1"
