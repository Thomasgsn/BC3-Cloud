"""Configuration stricte, secrets par fichier, aucun secret journalisé."""

import json
import os
import re
from pathlib import Path

ROOT = Path(os.getenv("BC3_ROOT", "/app"))
SECRET_DIR = Path(os.getenv("BC3_SECRET_DIR", "/run/secrets"))


def secrets():
    p = SECRET_DIR / "config.json"
    if not p.exists():
        raise RuntimeError("Configuration secrète absente : initialiser le profil local")
    return json.loads(p.read_text())


def setting(name, default):
    return os.getenv(name, default)


def database_ca():
    """CA SQL distincte de la CA des services internes sur RDS."""
    return setting("DB_SSLROOTCERT", str(SECRET_DIR / "ca.crt"))


def public_host():
    host = setting("BC3_PUBLIC_HOST", "bc3.local")
    if len(host) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")
    ):
        raise ValueError("Hôte public invalide : nom DNS explicite requis")
    return host
