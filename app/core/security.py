"""
Wallet signature verification for authentication.

Supports both EOA (ECDSA) and Smart Contract Wallet (ERC-1271/ERC-6492) signatures
for proving wallet ownership before sensitive operations like OAuth linking.
"""

import logging
import time
import traceback

from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_defunct
from fastapi import HTTPException
from web3 import Web3

from app.core.config import settings


def verify_wallet_signature(
    wallet_address: str,
    message: str,
    signature: str,
    timestamp: int | None = None,
    max_age_seconds: int = 300,
) -> bool:
    """
    Verify that a signature was created by the owner of the wallet address.
    
    Supports both EOA (65-byte ECDSA) and Smart Contract Wallet signatures (ERC-1271).
    
    Args:
        wallet_address: Ethereum wallet address (0x...)
        message: The message that was signed
        signature: The signature hex string (0x...)
        timestamp: Optional timestamp to check signature freshness
        max_age_seconds: Maximum age of signature in seconds (default 5 min)
    
    Returns:
        True if signature is valid
    
    Raises:
        HTTPException: If signature is invalid or too old
    """
    # Check timestamp freshness
    if timestamp is not None:
        now = int(time.time())
        if abs(now - timestamp) > max_age_seconds:
            raise HTTPException(
                status_code=401,
                detail="Signature timestamp is too old or in the future",
            )

    try:
        wallet_address = Web3.to_checksum_address(wallet_address)
        sig_hex = signature[2:] if signature.startswith("0x") else signature
        sig_length = len(sig_hex) // 2

        # EOA signature: 65 bytes (130 hex chars)
        if sig_length == 65:
            return _verify_eoa_signature(wallet_address, message, signature)
        else:
            return _verify_smart_wallet_signature(wallet_address, message, signature)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {str(e)}")


def _verify_eoa_signature(wallet_address: str, message: str, signature: str) -> bool:
    """Verify EOA (Externally Owned Account) signature using ECDSA recovery."""
    message_hash = encode_defunct(text=message)
    recovered_address = Account.recover_message(message_hash, signature=signature)

    if recovered_address.lower() != wallet_address.lower():
        raise HTTPException(
            status_code=401,
            detail="Signature does not match wallet address",
        )
    return True


def _verify_smart_wallet_signature(wallet_address: str, message: str, signature: str) -> bool:
    """
    Verify Smart Contract Wallet signature using ERC-1271 standard.
    
    The wallet's isValidSignature expects the EIP-191 personal_sign hash.
    """
    try:
        # Create EIP-191 hash that the wallet's isValidSignature expects
        message_hash_obj = encode_defunct(text=message)
        hash_bytes = _hash_eip191_message(message_hash_obj)

        if not isinstance(hash_bytes, bytes) or len(hash_bytes) != 32:
            raise ValueError(
                f"Hash must be 32 bytes, got {len(hash_bytes) if isinstance(hash_bytes, bytes) else 'N/A'}"
            )

        sig_bytes = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)

        # Get RPC URL
        rpc_url = settings.WEB3_RPC_URL or (
            "https://mainnet.base.org" if settings.ENV == "production"
            else "https://sepolia.base.org"
        )
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        # ERC-1271 magic value
        ERC1271_MAGIC_VALUE = "0x1626ba7e"

        # Check if contract is deployed
        code = w3.eth.get_code(wallet_address)
        if code == b"" or code == b"0x":
            # Check for ERC-6492 wrapper (undeployed wallet)
            erc6492_magic = "6492649264926492649264926492649264926492649264926492649264926492"
            if signature.lower().endswith(erc6492_magic):
                logging.warning(
                    f"ERC-6492 signature for undeployed wallet {wallet_address} - "
                    "full verification not implemented"
                )
                raise HTTPException(
                    status_code=401,
                    detail="Smart wallet signature verification failed: Contract not deployed, ERC-6492 verification not fully implemented.",
                )
            raise HTTPException(
                status_code=401,
                detail="Smart wallet signature verification failed: Contract not deployed",
            )

        # Contract is deployed - call isValidSignature(bytes32, bytes)
        from eth_abi import encode as abi_encode

        function_selector = "0x1626ba7e"
        encoded_params = abi_encode(["bytes32", "bytes"], [hash_bytes, sig_bytes])
        call_data = function_selector + encoded_params.hex()

        result = w3.eth.call({"to": wallet_address, "data": call_data})
        result_hex = "0x" + (result.hex() if isinstance(result, bytes) else result)

        if result_hex[:10].lower() != ERC1271_MAGIC_VALUE.lower():
            raise HTTPException(
                status_code=401,
                detail=f"Smart wallet signature verification failed: invalid magic value {result_hex[:10]}",
            )

        return True

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Smart wallet signature verification error: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=401,
            detail=f"Smart wallet signature verification failed: {str(e)}",
        )
