from __future__ import annotations

from typing import Any, Dict, List, Optional

from web3 import Web3

from app.core.config import settings


def _load_contract(w3: Web3):
    import json
    with open(settings.MOTIFY_CONTRACT_ABI_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    abi = raw.get("abi") if isinstance(raw, dict) and "abi" in raw else raw
    return w3.eth.contract(address=Web3.to_checksum_address(settings.MOTIFY_CONTRACT_ADDRESS), abi=abi)


def _ppm_to_bps(ppm: int) -> int:
    # 1 bps = 10,000 ppm; bps = round(ppm / 100)
    return int(round(int(ppm) / 100))


def _fee_params(w3: Web3) -> Dict[str, int]:
    """Decide fee params for the transaction.

    Priority:
      1) If MAX_FEE_GWEI set, use EIP-1559 cap from env with auto-derived priority (preferred)
    2) Else try EIP-1559 using latest block baseFee and a modest default priority fee
    3) Else fall back to node's gas_price
    """
    # 1) EIP-1559 caps from env, if provided (preferred)
    if settings.MAX_FEE_GWEI is not None:
        # Derive a conservative priority tip from node suggestions / fee history
        priority = None
        try:
            mpf = getattr(w3.eth, "max_priority_fee", None)
            if callable(mpf):
                priority = float(mpf()) / 1e9  # wei -> gwei
            elif isinstance(mpf, int):
                priority = float(mpf) / 1e9
        except Exception:
            priority = None
        if priority is None:
            try:
                fh = getattr(w3.eth, "fee_history", None)
                if callable(fh):
                    hist = fh(5, "latest", [50])
                    rewards = hist.get("reward") if isinstance(hist, dict) else None
                    if rewards and len(rewards) > 0 and len(rewards[-1]) > 0:
                        priority = float(rewards[-1][0]) / 1e9
            except Exception:
                priority = None
        if priority is None:
            priority = 0.1  # tiny fallback tip

        max_fee = float(settings.MAX_FEE_GWEI)
        return {
            "maxPriorityFeePerGas": w3.to_wei(priority, "gwei"),
            "maxFeePerGas": w3.to_wei(max_fee, "gwei"),
        }

    # 2) Try EIP-1559
    try:
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas") if isinstance(latest, dict) else getattr(latest, "baseFeePerGas", None)
        if base_fee is not None:
            try:
                # Try node suggestion if available; otherwise use a conservative 1 gwei priority
                priority = getattr(w3.eth, "max_priority_fee", None)
                if callable(priority):
                    priority_fee = int(priority())
                elif isinstance(priority, int):
                    priority_fee = int(priority)
                else:
                    priority_fee = int(w3.to_wei(1, "gwei"))
            except Exception:
                priority_fee = int(w3.to_wei(1, "gwei"))
            # Set a reasonable cap: 2x base + priority
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

    # Preview current fee params (for artifacts/visibility)
    fee_preview = _fee_params(w3)
    def _fee_mode(fp: Dict[str, int]) -> str:
        if "maxFeePerGas" in fp or "maxPriorityFeePerGas" in fp:
            # If env caps set, assume env mode, else auto
            return "eip1559-env" if (settings.MAX_FEE_GWEI is not None) else "eip1559-auto"
        if "gasPrice" in fp:
            return "legacy-fallback"
        return "unknown"
    fee_preview_mode = _fee_mode(fee_preview)

    if not send:
        return {"dry_run": True, "payload": payload, "fee_params_preview": fee_preview, "fee_params_preview_mode": fee_preview_mode}

    if not settings.PRIVATE_KEY:
        raise RuntimeError("PRIVATE_KEY not configured for sending transactions")

    account = w3.eth.account.from_key(settings.PRIVATE_KEY)

    tx_hashes: List[str] = []
    receipts: List[Dict[str, Any]] = []
    used_fee_params: List[Dict[str, Any]] = []
    nonce = w3.eth.get_transaction_count(account.address)

    for (participants, percentages) in chunks:
        fee = _fee_params(w3)
        used_fee_params.append({
            "params": {k: int(v) for k, v in fee.items()},
            "mode": _fee_mode(fee),
        })
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
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        if raw_tx is None:
            raise RuntimeError("SignedTransaction missing raw transaction bytes (web3 compat issue)")
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        tx_hash_hex = tx_hash.hex()
        tx_hashes.append(tx_hash_hex)

        # Wait for receipt (optional; could be async in production)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        # Normalize keys across different web3 versions
        r_status = int(getattr(receipt, "status", getattr(receipt, "status", 0)))
        r_gas_used = getattr(receipt, "gasUsed", None)
        if r_gas_used is None:
            r_gas_used = getattr(receipt, "gas_used", None)
        r_block = getattr(receipt, "blockNumber", None)
        if r_block is None:
            r_block = getattr(receipt, "block_number", None)
        # Some providers expose effectiveGasPrice; include when available
        eff = getattr(receipt, "effectiveGasPrice", None)
        if eff is None:
            eff = getattr(receipt, "effective_gas_price", None)
        receipts.append({
            "transactionHash": tx_hash_hex,
            "status": int(r_status if r_status is not None else 0),
            "gasUsed": int(r_gas_used if r_gas_used is not None else 0),
            "blockNumber": int(r_block if r_block is not None else 0),
            "effectiveGasPrice": int(eff) if eff is not None else None,
        })
        nonce += 1

    return {
        "dry_run": False,
        "payload": payload,
        "tx_hashes": tx_hashes,
        "receipts": receipts,
        "used_fee_params": used_fee_params,
        "fee_params_preview_mode": fee_preview_mode,
    }
