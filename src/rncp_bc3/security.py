"""Chiffrement authentifié, sessions et exports sans formules actives."""

import base64
import hashlib
import hmac
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import secrets as configuration


def key():
    return base64.urlsafe_b64decode(configuration()["encryption_key"])


def encrypt(value: bytes, context: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return b"BC3v1" + nonce + AESGCM(key()).encrypt(nonce, value, context.encode())


def decrypt(value: bytes, context: str, *, key_material: bytes | None = None) -> bytes:
    if not value.startswith(b"BC3v1") or len(value) < 33:
        raise ValueError("Format chiffré invalide")
    return AESGCM(key() if key_material is None else key_material).decrypt(
        value[5:17], value[17:], context.encode()
    )


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for(token):
    return hmac.new(key(), ("csrf:" + token).encode(), hashlib.sha256).hexdigest()


def csv_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def file_type(data: bytes, provided: str) -> str:
    if provided == "application/pdf" and data.startswith(b"%PDF-"):
        return provided
    if provided == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return provided
    raise ValueError("Type ou signature de fichier non autorisé : PDF ou PNG requis")
