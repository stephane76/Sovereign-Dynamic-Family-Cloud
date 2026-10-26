import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

DB = os.getenv("ADMISSION_DB", "/data/registry.sqlite3")
HEADSCALE = os.getenv("HEADSCALE_URL", "http://headscale:8080").rstrip("/")
KEY_FILE = os.getenv("HEADSCALE_API_KEY_FILE", "/run/secrets/headscale_api_key")
MAX_REQUEST_BYTES = 4096
CHALLENGE_TTL = 60
MAX_ISSUES_HOUR = 4
app = FastAPI(title="DFC ZTP Admission", docs_url=None, redoc_url=None, openapi_url=None)


def dbconn():
    db = sqlite3.connect(DB, timeout=10, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with dbconn() as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS devices(
            device_id TEXT PRIMARY KEY, public_key TEXT NOT NULL, site TEXT NOT NULL,
            role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'allowed',
            issued_count INTEGER NOT NULL DEFAULT 0, window_start INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS challenges(
            nonce_hash TEXT PRIMARY KEY, device_id TEXT NOT NULL,
            expires INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
          CREATE INDEX IF NOT EXISTS challenges_device ON challenges(device_id);
        """)


@app.on_event("startup")
def startup():
    init_db()


class Device(BaseModel):
    device_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,64}$")


class Admission(Device):
    nonce: str = Field(min_length=20, max_length=100)
    signature: str = Field(min_length=80, max_length=128)


@app.get("/healthz")
def health():
    with dbconn() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.middleware("http")
async def limit_body(request: Request, call_next):
    if request.headers.get("content-length") and int(request.headers["content-length"]) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "request too large")
    return await call_next(request)


@app.post("/v1/challenge")
def challenge(body: Device):
    now = int(time.time())
    with dbconn() as db:
        row = db.execute("SELECT status FROM devices WHERE device_id=?", (body.device_id,)).fetchone()
        if not row or row[0] != 'allowed':
            raise HTTPException(403, "device not authorized")
        db.execute("DELETE FROM challenges WHERE expires<?", (now,))
        db.execute("DELETE FROM challenges WHERE device_id=?", (body.device_id,))
        nonce = secrets.token_urlsafe(32)
        db.execute("INSERT INTO challenges(nonce_hash,device_id,expires) VALUES(?,?,?)", (hashlib.sha256(nonce.encode()).hexdigest(),body.device_id,now+CHALLENGE_TTL))
    return {"nonce":nonce,"expires_in":CHALLENGE_TTL, "signing_format":"dfc-admission-v1\\n{device_id}\\n{nonce}\\n"}


@app.post("/v1/admit")
def admit(body: Admission):
    now = int(time.time())
    nonce_hash = hashlib.sha256(body.nonce.encode()).hexdigest()
    # BEGIN IMMEDIATE serializes token issuance and consumes nonce before any upstream call.
    with dbconn() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT public_key,site,role,status,issued_count,window_start FROM devices WHERE device_id=?",(body.device_id,)).fetchone()
            nonce = db.execute("SELECT expires,consumed FROM challenges WHERE nonce_hash=? AND device_id=?",(nonce_hash,body.device_id)).fetchone()
            if not row or row[3]!='allowed' or not nonce or nonce[1] or nonce[0]<now:
                raise HTTPException(403,"not authorized or nonce expired/used")
            if row[5]>now-3600 and row[4]>=MAX_ISSUES_HOUR:
                raise HTTPException(429,"issuance rate exceeded")
            payload=f"dfc-admission-v1\n{body.device_id}\n{body.nonce}\n".encode()
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(row[0])).verify(base64.b64decode(body.signature,validate=True),payload)
            except (ValueError, binascii.Error, InvalidSignature) as exc:
                raise HTTPException(403,"invalid signature") from exc
            db.execute("UPDATE challenges SET consumed=1 WHERE nonce_hash=?",(nonce_hash,))
            db.execute("UPDATE devices SET issued_count=?,window_start=? WHERE device_id=?",(row[4]+1 if row[5]>now-3600 else 1,row[5] if row[5]>now-3600 else now,body.device_id))
            db.commit()
        except Exception:
            db.rollback()
            raise
    # A separate Headscale account must be assigned to the admission role.
    # Headscale v0.29.5 CreatePreAuthKeyRequest uses a NUMERIC user ID.
    try:
        token = Path(KEY_FILE).read_text().strip()
        if not token:
            raise ValueError("missing API token")
        expires = (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat().replace("+00:00","Z")
        request={"reusable":False,"ephemeral":False,"expiration":expires,"aclTags":[f"tag:{row[2]}"]}
        with httpx.Client(timeout=10) as client:
            response=client.post(f"{HEADSCALE}/api/v1/preauthkey",json=request,headers={"Authorization":f"Bearer {token}"})
            response.raise_for_status()
            key=response.json()["preAuthKey"]["key"]
    except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
        # Do NOT log credential or response body. Client can request a fresh challenge.
        raise HTTPException(502,"coordination temporarily unavailable") from exc
    return {"auth_key":key,"expires_in":300,"login_server":os.environ.get("PUBLIC_HEADSCALE_URL","https://headscale.yourfamily.eu"),"site":row[1],"role":row[2],"advertise_tag":f"tag:{row[2]}"}
