import hmac
import hashlib
import time
from fastapi import HTTPException


def verify_n8n_hmac(raw: bytes, sig: str | None, ts: str | None, secret: str):
    if not sig or not ts:
        raise HTTPException(401, "Missing signature headers")
    try:
        now = int(time.time())
        if abs(now - int(ts)) > 300:
            raise HTTPException(401, "Stale timestamp")
    except ValueError:
        raise HTTPException(401, "Invalid timestamp")
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, (sig or "").lower()):
        raise HTTPException(401, "Bad signature")
