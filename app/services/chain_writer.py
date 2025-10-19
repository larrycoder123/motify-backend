from __future__ import annotations

from typing import Any, Dict, List, Optional

from web3 import Web3

from app.core.config import settings


def _load_contract(w3: Web3):
    import json
    with open(settings.MOTIFY_CONTRACT_ABI_PATH, "r", encoding="utf-8") as f:
        abi = json.load(f)
    return w3.eth.contract(address=Web3.to_checksum_address(settings.MOTIFY_CONTRACT_ADDRESS), abi=abi)


def _ppm_to_bps(ppm: int) -> int:
    # 1 bps = 10,000 ppm; bps = round(ppm / 100)
    return int(round(int(ppm) / 100))


def _fee_params(w3: Web3) -> Dict[str, int]:
    """Decide fee params for the transaction.

    Priority:
      1) If GAS_PRICE_GWEI is set, use legacy gasPrice
      2) Else try EIP-1559 using latest block baseFee and suggested priority fee
      3) Else fall back to node's gas_price
    """
    # 1) Legacy override via env
    if settings.GAS_PRICE_GWEI is not None:
        return {"gasPrice": w3.to_wei(settings.GAS_PRICE_GWEI, "gwei")}

    # 2) Try EIP-1559
    try:
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas") if isinstance(latest, dict) else getattr(latest, "baseFeePerGas", None)
        if base_fee is not None:
            try:
                # web3 v6: property; v5: may not exist
                priority = getattr(w3.eth, "max_priority_fee", None)
                if callable(priority):
                    priority_fee = int(priority())
                elif isinstance(priority, int):
                    priority_fee = int(priority)
                else:
                    # fallback to 2 gwei priority
                    priority_fee = w3.to_wei(2, "gwei")
            except Exception:
                priority_fee = w3.to_wei(2, "gwei")
            max_fee = int(base_fee) * 2 + int(priority_fee)
            return {"maxFeePerGas": int(max_fee), "maxPriorityFeePerGas": int(priority_fee)}
    except Exception:
        pass

    # 3) Fallback to legacy node gas price
    try:
        return {"gasPrice": int(w3.eth.gas_price)}
    except Exception:
        return {}


def declare_results(
    challenge_id: int,
    items: List[Dict[str, Any]],
    *,
    chunk_size: int = 200,
    send: bool = False,
) -> Dict[str, Any]:
    """Declare results on-chain.

    items: [{ user, stake_minor_units, percent_ppm }]
    Converts percent_ppm -> basis points (0..10_000) as per contract expectation.
    If send=False, returns payload preview without broadcasting.
    """
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise RuntimeError("Web3 not configured for chain writer")

    w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
    # Optional PoA middleware (e.g., some L2s/PoA chains). Be tolerant to web3 version differences.
    try:
        # web3.py v5 style
        from web3.middleware import geth_poa_middleware  # type: ignore
        try:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception:
            pass
    except Exception:
        try:
            # web3.py v6 style
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware  # type: ignore
            try:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception:
                pass
        except Exception:
            # No-op if neither is available
            pass

    contract = _load_contract(w3)

    # Build arrays
    addrs: List[str] = []
    bps: List[int] = []
    for it in items:
        addrs.append(Web3.to_checksum_address(it["user"]))
        bps.append(_ppm_to_bps(int(it["percent_ppm"])) )

    # Chunking
    chunks = []
    for i in range(0, len(addrs), chunk_size):
        chunks.append((addrs[i:i+chunk_size], bps[i:i+chunk_size]))

    payload = {
        "challenge_id": int(challenge_id),
        "chunks": [
            {"participants": part, "refundPercentages": perc}
            for (part, perc) in chunks
        ],
    }

    if not send:
        return {"dry_run": True, "payload": payload}

    if not settings.PRIVATE_KEY:
        raise RuntimeError("PRIVATE_KEY not configured for sending transactions")

    account = w3.eth.account.from_key(settings.PRIVATE_KEY)

    tx_hashes: List[str] = []
    receipts: List[Dict[str, Any]] = []
    nonce = w3.eth.get_transaction_count(account.address)

    for (participants, percentages) in chunks:
        fee = _fee_params(w3)
        tx = contract.functions.declareResults(int(challenge_id), participants, percentages).build_transaction({
            "from": account.address,
            "nonce": nonce,
            **fee,
        })
        # Gas limit estimation if not provided
        if settings.GAS_LIMIT is not None:
            tx["gas"] = int(settings.GAS_LIMIT)
        else:
            try:
                tx["gas"] = w3.eth.estimate_gas(tx)  # may raise
            except Exception:
                # fallback gas limit; caller can override via env
                tx["gas"] = 1_000_000

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        tx_hashes.append(tx_hash_hex)

        # Wait for receipt (optional; could be async in production)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        receipts.append({
            "transactionHash": tx_hash_hex,
            "status": int(receipt.status),
            "gasUsed": int(receipt.gasUsed),
            "blockNumber": int(receipt.blockNumber),
        })
        nonce += 1

    return {"dry_run": False, "payload": payload, "tx_hashes": tx_hashes, "receipts": receipts}
