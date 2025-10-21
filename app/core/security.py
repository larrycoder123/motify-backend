import hmac
import hashlib
import time
from fastapi import HTTPException
from eth_account.messages import encode_defunct
from eth_account import Account
from web3 import Web3


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


def verify_wallet_signature(
    wallet_address: str,
    message: str,
    signature: str,
    timestamp: int | None = None,
    max_age_seconds: int = 300
) -> bool:
    """
    Verify that a signature was created by the owner of the wallet address.

    Args:
        wallet_address: The Ethereum wallet address (0x...)
        message: The message that was signed
        signature: The signature hex string (0x...)
        timestamp: Optional timestamp to check signature freshness
        max_age_seconds: Maximum age of signature in seconds (default 5 min)

    Returns:
        bool: True if signature is valid

    Raises:
        HTTPException: If signature is invalid or too old
    """
    # Check timestamp freshness if provided
    if timestamp is not None:
        now = int(time.time())
        if abs(now - timestamp) > max_age_seconds:
            raise HTTPException(
                status_code=401,
                detail="Signature timestamp is too old or in the future"
            )

    try:
        # Normalize addresses
        wallet_address = Web3.to_checksum_address(wallet_address)

        # Encode the message
        message_hash = encode_defunct(text=message)

        # Recover the address from signature
        recovered_address = Account.recover_message(
            message_hash, signature=signature)

        # Compare addresses (case-insensitive)
        if recovered_address.lower() != wallet_address.lower():
            raise HTTPException(
                status_code=401,
                detail="Signature does not match wallet address"
            )

        return True

    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid signature format: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Signature verification failed: {str(e)}")
