"""Créer un compte local avec mot de passe lu par fichier, jamais en argument/log."""

import argparse
import json
import re
import uuid
from pathlib import Path

from argon2 import PasswordHasher

from rncp_bc3 import db

p = argparse.ArgumentParser()
p.add_argument("--username", required=True)
p.add_argument("--role", choices=["requester", "agent"], required=True)
p.add_argument("--password-file", required=True)
a = p.parse_args()
if not re.fullmatch(r"[a-z0-9_.-]{3,64}", a.username):
    raise ValueError("Nom de compte invalide")
password = Path(a.password_file).read_text().strip()
if len(password) < 14:
    raise ValueError("Mot de passe trop court")
db.migrate()
with db.connect() as c:
    row = c.execute("SELECT role FROM users WHERE username=%s", (a.username,)).fetchone()
    if row:
        if row["role"] != a.role:
            raise ValueError("Compte déjà présent avec un autre rôle")
        event = "user_already_exists_no_password_changed"
    else:
        c.execute(
            "INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
            (
                uuid.uuid4(),
                a.username,
                PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(password),
                a.role,
            ),
        )
        event = "user_created"
print(
    json.dumps(
        {
            "event": event,
            "username": a.username,
            "role": a.role,
            "secret_printed": False,
        }
    )
)
