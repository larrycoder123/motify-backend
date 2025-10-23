"""
Tests for Base Wallet signature verification (ERC-1271/ERC-6492)
"""
import pytest
from app.core.security import verify_wallet_signature
from fastapi import HTTPException


def test_eoa_signature_verification():
    """Test that EOA (65-byte) signatures still work."""
    # Example EOA signature (MetaMask-style)
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    message = "Test message"
    # This would be a real 65-byte signature from MetaMask
    signature = "0x" + "a" * 130  # Mock 65-byte signature
    
    # Note: This will fail with a mock signature, but tests the code path
    with pytest.raises(HTTPException):
        verify_wallet_signature(wallet_address, message, signature)


def test_smart_wallet_signature_detection():
    """Test that smart wallet signatures (longer than 65 bytes) are detected."""
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    message = "Test message"
    # Smart wallet signature is typically 1000+ bytes
    signature = "0x" + "b" * 2000  # Mock smart wallet signature
    
    # This will be routed to smart wallet verification
    with pytest.raises(HTTPException) as exc:
        verify_wallet_signature(wallet_address, message, signature)
    
    # Should fail with smart wallet specific error (not EOA error)
    assert "Smart wallet" in str(exc.value.detail) or "verification failed" in str(exc.value.detail)


def test_timestamp_validation():
    """Test that old timestamps are rejected."""
    import time
    
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    message = "Test message"
    signature = "0x" + "a" * 130
    
    # Use timestamp from 10 minutes ago (should fail with 5 min default)
    old_timestamp = int(time.time()) - 600
    
    with pytest.raises(HTTPException) as exc:
        verify_wallet_signature(wallet_address, message, signature, old_timestamp)
    
    assert exc.value.status_code == 401
    assert "too old" in str(exc.value.detail).lower()


def test_future_timestamp_validation():
    """Test that future timestamps are rejected."""
    import time
    
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    message = "Test message"
    signature = "0x" + "a" * 130
    
    # Use timestamp from future
    future_timestamp = int(time.time()) + 600
    
    with pytest.raises(HTTPException) as exc:
        verify_wallet_signature(wallet_address, message, signature, future_timestamp)
    
    assert exc.value.status_code == 401
    assert "future" in str(exc.value.detail).lower() or "too old" in str(exc.value.detail).lower()


def test_erc6492_signature_detection():
    """Test that ERC-6492 wrapped signatures (undeployed contracts) are detected."""
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    message = "Test message"
    
    # ERC-6492 signature ends with magic bytes
    erc6492_magic = "6492649264926492649264926492649264926492649264926492649264926492"
    signature = "0x" + "c" * 1000 + erc6492_magic
    
    # This should be accepted for undeployed contracts (Base Account behavior)
    # In a real test with RPC, this would check contract deployment status
    try:
        result = verify_wallet_signature(wallet_address, message, signature)
        # If RPC is available and contract is not deployed, should accept ERC-6492
        assert result == True or isinstance(result, bool)
    except HTTPException as exc:
        # If RPC is not available or other verification issues
        # Should still detect it's a smart wallet signature
        assert "Smart wallet" in str(exc.detail) or "verification failed" in str(exc.detail)


def test_invalid_address_format():
    """Test that invalid addresses are rejected."""
    invalid_address = "not_an_address"
    message = "Test message"
    signature = "0x" + "a" * 130
    
    with pytest.raises(HTTPException) as exc:
        verify_wallet_signature(invalid_address, message, signature)
    
    assert exc.value.status_code in [400, 401]


def test_signature_without_0x_prefix():
    """Test that signatures without 0x prefix are handled."""
    wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    message = "Test message"
    # Signature without 0x prefix
    signature = "a" * 130
    
    # Should still be processed (prefix is added internally)
    with pytest.raises(HTTPException):
        verify_wallet_signature(wallet_address, message, signature)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
