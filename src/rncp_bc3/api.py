"""API de support : authentification réelle, accès contrôlés, fichiers privés et jobs."""

import asyncio
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from . import db, storage
from .config import public_host, setting
from .security import csrf_for, decrypt, encrypt, file_type, key, token_hash

LOG = logging.getLogger("bc3")
logging.basicConfig(level=logging.INFO, format="%(message)s")
REQUESTS = Counter("bc3_http_requests_total", "Requêtes HTTP", ["method", "route", "status"])
LATENCY = Histogram(
    "bc3_http_duration_seconds",
    "Durée HTTP",
    ["route"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)
HASH = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY = HASH.hash("unavailable-account-random-dummy")
COOKIE = "__Host-bc3"
MAX_FILE = 5 * 1024 * 1024
ORIGINS = set(
    setting(
        "BC3_ORIGINS",
        "https://localhost:8454,https://127.0.0.1:8454,https://bc3.local:8454,https://localhost:8453,https://front:8443",
    ).split(",")
)


@asynccontextmanager
async def lifespan(app):
    for attempt in range(40):
        try:
            db.migrate()
            storage.initialize()
            break
        except Exception as e:
            if attempt == 39:
                raise
            LOG.info(
                json.dumps(
                    {
                        "event": "startup_wait",
                        "attempt": attempt + 1,
                        "error_type": type(e).__name__,
                    }
                )
            )
            await asyncio.sleep(2)
    yield


app = FastAPI(title="BC3 Support", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "api",
        "front",
        "localhost",
        "127.0.0.1",
        "bc3.local",
        public_host(),
        setting("POD_IP", "127.0.0.1"),
    ],
)


@app.middleware("http")
async def controls(request: Request, call_next):
    start = time.monotonic()
    if (
        request.method not in ["GET", "HEAD", "OPTIONS"]
        and request.headers.get("origin") not in ORIGINS
    ):
        return JSONResponse({"detail": "Origine non autorisée"}, status_code=403)
    response = await call_next(request)
    route = request.scope.get("route")
    label = route.path if route else "unmatched"
    if label != "/metrics":
        REQUESTS.labels(request.method, label, str(response.status_code)).inc()
        LATENCY.labels(label).observe(time.monotonic() - start)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
    )
    return response


@app.exception_handler(ClientError)
async def storage_error(request, error):
    return JSONResponse({"detail": "Stockage indisponible, aucune substitution"}, status_code=503)


@app.exception_handler(BotoCoreError)
async def transport_error(request, error):
    return JSONResponse(
        {"detail": "Transport indisponible, réessayer ultérieurement"}, status_code=503
    )


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=200)


class TicketInput(Strict):
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=3, max_length=10000)


class TicketPatch(Strict):
    status: Literal["open", "in_progress", "closed"]
    version: int = Field(ge=1)
    assign_to_self: bool = False


def identity(request: Request):
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 200:
        raise HTTPException(401, "Authentification requise")
    with db.connect() as c:
        user = c.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=%s AND expires_at>now()",
            (token_hash(token),),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Session absente ou expirée")
    if request.method not in ["GET", "HEAD", "OPTIONS"] and not hmac.compare_digest(
        request.headers.get("x-csrf-token", ""), csrf_for(token)
    ):
        raise HTTPException(403, "Jeton CSRF invalide")
    return user


UserIdentity = Annotated[dict, Depends(identity)]


def can_read(ticket, user):
    return user["role"] == "agent" or ticket["owner_id"] == user["id"]


def ticket_record(c, ticket_id, user):
    row = c.execute("SELECT * FROM tickets WHERE id=%s", (ticket_id,)).fetchone()
    if not row or not can_read(row, user):
        raise HTTPException(404, "Ticket introuvable")
    return row


def view_ticket(row, *, encryption_key: bytes | None = None):
    return {
        "id": str(row["id"]),
        "title": decrypt(
            bytes(row["title"]), str(row["id"]) + ":title", key_material=encryption_key
        ).decode(),
        "body": decrypt(
            bytes(row["body"]), str(row["id"]) + ":body", key_material=encryption_key
        ).decode(),
        "status": row["status"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "owner_id": str(row["owner_id"]),
        "assignee_id": str(row["assignee_id"]) if row["assignee_id"] else None,
    }


@app.post("/api/login")
def login(data: Credentials, response: Response):
    with db.connect() as c:
        count = c.execute(
            "SELECT count(*) n FROM audit WHERE event='login_failed' AND actor=%s AND at>now()-interval '5 minutes'",
            (data.username,),
        ).fetchone()["n"]
        if count >= 10:
            raise HTTPException(429, "Trop de tentatives, réessayer plus tard")
        user = c.execute("SELECT * FROM users WHERE username=%s", (data.username,)).fetchone()
    try:
        HASH.verify(user["password_hash"] if user else DUMMY, data.password)
        ok = user is not None
    except (VerifyMismatchError, VerificationError):
        ok = False
    if not ok:
        db.audit("login_failed", data.username)
        raise HTTPException(401, "Identifiants invalides")
    token = secrets.token_urlsafe(32)
    with db.connect() as c:
        c.execute("DELETE FROM sessions WHERE expires_at<now()")
        c.execute(
            "INSERT INTO sessions VALUES (%s,%s,%s)",
            (
                token_hash(token),
                user["id"],
                datetime.now(UTC) + timedelta(hours=1),
            ),
        )
    response.set_cookie(
        COOKIE,
        token,
        secure=True,
        httponly=True,
        samesite="strict",
        max_age=3600,
        path="/",
    )
    db.audit("login_success", str(user["id"]))
    return {"username": user["username"], "role": user["role"], "csrf": csrf_for(token)}


@app.get("/api/me")
def me(request: Request, user: UserIdentity):
    return {
        "username": user["username"],
        "role": user["role"],
        "csrf": csrf_for(request.cookies[COOKIE]),
    }


@app.post("/api/logout")
def logout(request: Request, response: Response, user: UserIdentity):
    with db.connect() as c:
        c.execute(
            "DELETE FROM sessions WHERE token_hash=%s",
            (token_hash(request.cookies[COOKIE]),),
        )
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
    return {"logged_out": True}


@app.get("/api/tickets")
def tickets(user: UserIdentity):
    with db.connect() as c:
        rows = c.execute(
            "SELECT * FROM tickets WHERE (%s OR owner_id=%s) ORDER BY created_at DESC LIMIT 200",
            (user["role"] == "agent", user["id"]),
        ).fetchall()
    encryption_key = key() if rows else None
    return [view_ticket(r, encryption_key=encryption_key) for r in rows]


@app.post("/api/tickets", status_code=201)
def create_ticket(data: TicketInput, user: UserIdentity):
    i = uuid.uuid4()
    with db.connect() as c:
        row = c.execute(
            "INSERT INTO tickets(id,owner_id,title,body) VALUES (%s,%s,%s,%s) RETURNING *",
            (
                i,
                user["id"],
                encrypt(data.title.encode(), str(i) + ":title"),
                encrypt(data.body.encode(), str(i) + ":body"),
            ),
        ).fetchone()
    db.audit("ticket_created", str(user["id"]))
    return view_ticket(row)


@app.get("/api/tickets/{ticket_id}")
def detail(ticket_id: uuid.UUID, user: UserIdentity):
    with db.connect() as c:
        return view_ticket(ticket_record(c, ticket_id, user))


@app.patch("/api/tickets/{ticket_id}")
def update(ticket_id: uuid.UUID, data: TicketPatch, user: UserIdentity):
    if user["role"] != "agent":
        raise HTTPException(403, "Rôle agent requis")
    with db.connect() as c:
        row = c.execute(
            "UPDATE tickets SET status=%s,version=version+1,assignee_id=CASE WHEN %s THEN %s ELSE assignee_id END WHERE id=%s AND version=%s RETURNING *",
            (data.status, data.assign_to_self, user["id"], ticket_id, data.version),
        ).fetchone()
        if not row:
            raise HTTPException(409, "Ticket modifié ou introuvable, recharger avant de réessayer")
    return view_ticket(row)


@app.post("/api/tickets/{ticket_id}/attachments", status_code=201)
async def upload(ticket_id: uuid.UUID, request: Request, user: UserIdentity):
    with db.connect() as c:
        ticket_record(c, ticket_id, user)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_FILE:
            raise HTTPException(413, "Fichier limité à 5 Mio")
    if not data:
        raise HTTPException(422, "Fichier vide")
    try:
        mime = file_type(bytes(data), request.headers.get("content-type", ""))
    except ValueError as e:
        raise HTTPException(415, str(e)) from e
    i = uuid.uuid4()
    key = f"attachments/{i}"
    sha = storage.put(key, bytes(data))
    try:
        with db.connect() as c:
            c.execute(
                "INSERT INTO attachments(id,ticket_id,object_key,mime,size,sha256) VALUES (%s,%s,%s,%s,%s,%s)",
                (i, ticket_id, key, mime, len(data), sha),
            )
    except Exception:
        storage.client().delete_object(Bucket=storage.BUCKET, Key=key)
        raise
    return {"id": str(i), "size": len(data), "sha256": sha, "mime": mime}


@app.get("/api/tickets/{ticket_id}/attachments")
def attachments(ticket_id: uuid.UUID, user: UserIdentity):
    with db.connect() as c:
        ticket_record(c, ticket_id, user)
        rows = c.execute(
            "SELECT id,mime,size,sha256 FROM attachments WHERE ticket_id=%s",
            (ticket_id,),
        ).fetchall()
    return rows


@app.get("/api/attachments/{attachment_id}")
def attachment(attachment_id: uuid.UUID, user: UserIdentity):
    with db.connect() as c:
        row = c.execute(
            "SELECT a.*,t.owner_id FROM attachments a JOIN tickets t ON a.ticket_id=t.id WHERE a.id=%s",
            (attachment_id,),
        ).fetchone()
        if not row or not can_read(row, user):
            raise HTTPException(404, "Fichier introuvable")
    data = storage.get(row["object_key"], row["sha256"])
    ext = "pdf" if row["mime"] == "application/pdf" else "png"
    return Response(
        data,
        media_type=row["mime"],
        headers={
            "Content-Disposition": f'attachment; filename="piece-{attachment_id}.{ext}"',
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@app.post("/api/exports", status_code=202)
def export(user: UserIdentity):
    i = uuid.uuid4()
    with db.connect() as c:
        active = c.execute(
            "SELECT count(*) n FROM exports WHERE requester_id=%s AND status IN ('pending','processing')",
            (user["id"],),
        ).fetchone()["n"]
        if active >= 3:
            raise HTTPException(429, "Trois exports sont déjà en attente")
        c.execute("INSERT INTO exports(id,requester_id) VALUES (%s,%s)", (i, user["id"]))
    try:
        storage.enqueue(i)
    except (BotoCoreError, ClientError):
        LOG.warning(json.dumps({"event": "enqueue_deferred", "job_id": str(i)}))
    return {"id": str(i), "status": "pending"}


@app.get("/api/exports")
def exports(user: UserIdentity):
    with db.connect() as c:
        return c.execute(
            "SELECT id,status,attempts,created_at,error_code FROM exports WHERE requester_id=%s ORDER BY created_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()


@app.get("/api/exports/{export_id}")
def export_detail(export_id: uuid.UUID, user: UserIdentity):
    with db.connect() as c:
        row = c.execute(
            "SELECT id,status,attempts,sha256,error_code FROM exports WHERE id=%s AND requester_id=%s",
            (export_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Export introuvable")
    return row


@app.get("/api/exports/{export_id}/download")
def export_download(export_id: uuid.UUID, user: UserIdentity):
    with db.connect() as c:
        row = c.execute(
            "SELECT * FROM exports WHERE id=%s AND requester_id=%s AND status='complete'",
            (export_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Export indisponible")
    return Response(
        storage.get(row["object_key"], row["sha256"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="export-{export_id}.csv"'},
    )


@app.post("/api/tickets/{ticket_id}/intent")
def ticket_intent(ticket_id: uuid.UUID, user: UserIdentity):
    from .intent import suggest

    with db.connect() as c:
        row = view_ticket(ticket_record(c, ticket_id, user))
    try:
        return suggest(row["title"] + " " + row["body"])
    except (OSError, ValueError, KeyError):
        raise HTTPException(503, "Modèle indisponible ou intégrité refusée") from None


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    with db.connect() as c:
        c.execute("SELECT 1")
    return {"status": "ready", "version": "1.3.0"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_keyfile=str(Path(setting("BC3_TLS_DIR", "/run/tls")) / "server.key"),
        ssl_certfile=str(Path(setting("BC3_TLS_DIR", "/run/tls")) / "server.crt"),
        access_log=False,
    )
