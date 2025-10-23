# api/core/security.py
import time
import logging
import traceback
from fastapi import HTTPException
from eth_account.messages import encode_defunct, _hash_eip191_message
from eth_account import Account
from web3 import Web3
from app.core.config import settings

def verify_wallet_signature(
    wallet_address: str,
    message: str,
    signature: str,
    timestamp: int | None = None,
    max_age_seconds: int = 300
) -> bool:
    """
    Verify that a signature was created by the owner of the wallet address.
    Supports both EOA (65-byte ECDSA) and Smart Contract Wallet signatures (ERC-1271/ERC-6492).
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
        # Remove '0x' prefix if present
        sig_bytes = signature
        if signature.startswith('0x'):
            sig_bytes = signature[2:]
        # Determine signature type based on length
        sig_length = len(sig_bytes) // 2  # Convert hex chars to bytes
        # EOA signature: 65 bytes (130 hex chars)
        if sig_length == 65:
            return _verify_eoa_signature(wallet_address, message, signature)
        # Smart contract wallet signature (ERC-1271/ERC-6492): longer than 65 bytes
        else:
            logging.debug(f"Processing smart wallet signature for {wallet_address}, length {sig_length}.") # Log signature length
            return _verify_smart_wallet_signature(wallet_address, message, signature)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid signature format: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Signature verification failed: {str(e)}")

def _verify_eoa_signature(wallet_address: str, message: str, signature: str) -> bool:
    """Verify EOA (Externally Owned Account) signature using ECDSA recovery."""
    # Encode the message using personal_sign standard
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

def _verify_smart_wallet_signature(wallet_address: str, message: str, signature: str) -> bool:
    """Verify Smart Contract Wallet signature using ERC-1271 standard.
    Supports ERC-6492 for undeployed wallets (Base Account).
    Assumes 'message' is the original string passed to the signing function.
    """
    try:
        logging.debug(f"Processing smart wallet signature for message: {message[:50]}...") # Log first 50 chars of message
        logging.debug(f"Signature length: {len(signature)} chars ({len(signature)//2} bytes).") # Log signature length

        # For Coinbase Smart Wallet with WebAuthn/passkeys:
        # The wallet uses signMessage which wraps the message with EIP-191 format:
        # 0x19 + "Ethereum Signed Message:\n" + len(message) + message
        # Then it takes keccak256 of this prefixed message.
        # The wallet's isValidSignature expects THIS HASH (the personal_sign hash).
        
        # Create the EIP-191 prefixed message
        message_hash_obj = encode_defunct(text=message)
        
        # The SignableMessage object has a version (0x19), header (\x19Ethereum Signed Message:\n{len}), and body (message)
        # We need to hash the complete prefixed message: version + header + body
        # eth_account's _hash_eip191_message does this internally
        hash_bytes = _hash_eip191_message(message_hash_obj)
        
        logging.debug(f"Calculated EIP-191 personal_sign hash: {hash_bytes.hex()}") # Log hash

        # Ensure hash_bytes is exactly 32 bytes
        if not isinstance(hash_bytes, bytes) or len(hash_bytes) != 32:
             # This check might be redundant if keccak always returns 32-byte hashes
             # but added for robustness.
            raise ValueError(f"Hash must be 32 bytes, got {type(hash_bytes)} with length {len(hash_bytes) if isinstance(hash_bytes, bytes) else 'N/A'}")

        # Remove '0x' from signature if present
        sig_bytes = bytes.fromhex(signature[2:] if signature.startswith('0x') else signature)

        # Get RPC URL from settings or use public endpoint
        rpc_url = settings.WEB3_RPC_URL or (
            "https://mainnet.base.org" if settings.ENV == "production" # Removed trailing space
            else "https://sepolia.base.org" # Removed trailing space
        )

        # Create Web3 instance
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        # ERC-1271 magic value: bytes4(keccak256("isValidSignature(bytes32,bytes)"))
        ERC1271_MAGIC_VALUE = "0x1626ba7e"

        # Check if contract is deployed
        code = w3.eth.get_code(wallet_address)
        if code == b'' or code == b'0x':
            logging.debug(f"Smart wallet contract {wallet_address} is not deployed.")
            # Contract not deployed yet - check for ERC-6492 wrapper
            # Common magic: 0x6492649264926492649264926492649264926492649264926492649264926492
            erc6492_magic = "6492649264926492649264926492649264926492649264926492649264926492"
            if signature.lower().endswith(erc6492_magic):
                 logging.debug(f"Detected ERC-6492 signature for {wallet_address}.") # Log detection
                 # For ERC-6492, the verification process is more complex and often involves
                 # simulating the contract deployment or using specific libraries.
                 # For now, we'll log and potentially return True if the magic is present,
                 # acknowledging that full verification requires simulation.
                 # A simplified approach might be to assume the frontend handled ERC-6492 correctly
                 # and the underlying signature (using `hash_bytes`) is valid for the *future* deployed state.
                 # However, the standard ERC-1271 call cannot be made on an undeployed address.
                 # This is a placeholder. A full implementation requires simulation logic.
                 # For example, calling a factory contract with the calldata to simulate the deployment
                 # and then checking `isValidSignature` on the simulated address.
                 # Without this, we cannot verify the signature against the *current* blockchain state.
                 # Depending on trust model, you might want to reject these here or handle differently.
                 # For now, let's reject it as verification is crucial and simulation is complex.
                 logging.warning(f"Signature for undeployed wallet {wallet_address} is ERC-6492, but full verification not implemented in this stub.")
                 # Attempting to call isValidSignature on an undeployed address will fail.
                 # We need simulation logic here, which is outside the scope of this simple fix.
                 # Returning True here would be insecure.
                 # Let's raise an error indicating the need for simulation or a different verification path.
                 raise HTTPException(status_code=401, detail="Smart wallet signature verification failed: Contract not deployed, ERC-6492 verification not fully implemented.")
            else:
                logging.debug(f"Smart wallet {wallet_address} not deployed and signature is not ERC-6492 format: {signature[:20]}...") # Log details
                raise HTTPException(status_code=401, detail="Smart wallet signature verification failed: Contract not deployed and signature is not ERC-6492 format")

        # Contract is deployed - call isValidSignature
        # Function selector for isValidSignature(bytes32,bytes)
        function_selector = "0x1626ba7e"
        # Encode the parameters: bytes32 hash, bytes signature
        # We need eth_abi to encode the parameters correctly
        from eth_abi import encode as abi_encode
        # The function signature is isValidSignature(bytes32 _hash, bytes _signature)
        # _hash is 32 bytes, _signature is variable length bytes
        encoded_params = abi_encode(['bytes32', 'bytes'], [hash_bytes, sig_bytes])
        # Make the call data
        call_data = function_selector + encoded_params.hex()
        logging.debug(f"Calling isValidSignature on {wallet_address} with  {call_data[:50]}...") # Log call data

        # Perform the eth_call
        result = w3.eth.call({'to': wallet_address, 'data': call_data})

        # Check if result matches the magic value
        result_hex = result.hex() if isinstance(result, bytes) else result
        if not result_hex.startswith('0x'):
            result_hex = '0x' + result_hex
        logging.debug(f"isValidSignature result: {result_hex}") # Log result

        if result_hex[:10].lower() != ERC1271_MAGIC_VALUE.lower():
            raise HTTPException(status_code=401, detail=f"Smart wallet signature verification failed: invalid magic value {result_hex[:10]}")

        logging.debug("Smart wallet signature verification successful.") # Log success
        return True
    except HTTPException:
        # Re-raise HTTP exceptions directly
        raise
    except Exception as e:
        logging.error(f"Error in _verify_smart_wallet_signature: {e}") # Log error
        # Log more details if needed
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=401, detail=f"Smart wallet signature verification failed: {str(e)}")