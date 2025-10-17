import time
import hmac
import hashlib
import pytest

from app.core.security import verify_n8n_hmac


def test_verify_n8n_hmac_ok():
    secret = "s"
    raw = b"{}"
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    # should not raise
    verify_n8n_hmac(raw, sig, ts, secret)


def test_verify_n8n_hmac_stale():
    secret = "s"
    raw = b"{}"
    ts = str(int(time.time()) - 1000)  # > 300s
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    with pytest.raises(Exception):
        verify_n8n_hmac(raw, sig, ts, secret)
