from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Dict, Any


@dataclass
class ListenerConfig:
    rpc_url: str
    contract_address: str
    abi_path: str
    confirmations: int = 2
    poll_seconds: float = 5.0
    start_block: Optional[int] = None


class Web3Listener:
    def __init__(self, cfg: ListenerConfig):
        try:
            from web3 import Web3
        except Exception as e:  # pragma: no cover
            raise RuntimeError("web3.py not installed; add 'web3' to requirements and install") from e

        self._Web3 = Web3
        self.cfg = cfg
        self.w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 15}))
        if not self.w3.is_connected():  # web3>=6
            raise RuntimeError("Failed to connect to WEB3_RPC_URL")

        abi = json.loads(Path(cfg.abi_path).read_text(encoding="utf-8"))
        self.contract = self.w3.eth.contract(address=self.w3.to_checksum_address(cfg.contract_address), abi=abi)

    def poll_loop(self, on_challenge_created: Callable[[Dict[str, Any]], None], stop_condition: Callable[[], bool] | None = None):
        """Poll for ChallengeCreated events and call on_challenge_created(challenge_id, creator).
        stop_condition: optional callable returning True to exit loop.
        """
        # Determine initial block
        try:
            current = self.w3.eth.block_number
        except Exception as e:  # pragma: no cover
            logging.error("web3: get block number failed: %s", e)
            return

        next_from = self.cfg.start_block or max(0, current - 1000)  # tail range by default

        try:
            event_cls = getattr(self.contract.events, "ChallengeCreated")
        except Exception:
            logging.error("ABI missing 'ChallengeCreated' event definition")
            return

        MAX_RANGE = 250  # avoid provider log size limits
        while True:
            if stop_condition and stop_condition():
                return
            try:
                latest = self.w3.eth.block_number
                # Wait for confirmations
                to_block = max(self.cfg.start_block or 0, latest - max(0, int(self.cfg.confirmations)))
                if to_block >= next_from:
                    # Fetch logs in bounded, chunked ranges to avoid provider limits
                    slice_start = next_from
                    while slice_start <= to_block:
                        slice_end = min(slice_start + MAX_RANGE - 1, to_block)
                        try:
                            logs = event_cls.get_logs(from_block=slice_start, to_block=slice_end)
                        except Exception as e:
                            logging.warning("web3 get_logs error range=[%s,%s]: %s", slice_start, slice_end, e)
                            # Move slice forward to avoid stalling on a bad range
                            slice_start = slice_end + 1
                            continue
                        for log in logs:
                            # Event args decoding is handled by web3
                            if hasattr(log, "args"):
                                args = dict(getattr(log, "args") or {})
                            else:
                                # fallback if already dict-like
                                args = (log.get("args") if isinstance(log, dict) else {}) or {}
                            challenge_id = int(args.get("challengeId") or args.get("challenge_id"))
                            creator = str(args.get("creator") or args.get("owner") or args.get("owner_wallet") or "")
                            recipient = str(args.get("recipient") or "")
                            end_time = int(args.get("endTime") or 0)
                            is_private = bool(args.get("isPrivate") or False)
                            metadata_hash = args.get("metadataHash")
                            # normalize metadata hash to 0x-prefixed string
                            if metadata_hash is not None:
                                # HexBytes or bytes → hex string
                                try:
                                    metadata_hash = metadata_hash.hex() if hasattr(metadata_hash, "hex") else str(metadata_hash)
                                except Exception:
                                    metadata_hash = str(metadata_hash)
                                if not metadata_hash.startswith("0x") and len(metadata_hash) in (64, 66):
                                    # ensure 0x prefix
                                    metadata_hash = metadata_hash if metadata_hash.startswith("0x") else ("0x" + metadata_hash)
                                metadata_hash = metadata_hash.lower()
                            # tx hash and block number
                            if isinstance(log, dict):
                                bn = log.get("blockNumber")
                                th = log.get("transactionHash")
                            else:
                                bn = getattr(log, "blockNumber", None)
                                th = getattr(log, "transactionHash", None)
                            tx_hash = None
                            if th is not None:
                                try:
                                    tx_hash = th.hex() if hasattr(th, "hex") else str(th)
                                except Exception:
                                    tx_hash = str(th)
                            event_data = {
                                "challenge_id": challenge_id,
                                "creator": creator,
                                "recipient": recipient,
                                "end_time": end_time,
                                "is_private": is_private,
                                "metadata_hash": metadata_hash,
                                "blockNumber": bn,
                                "transactionHash": tx_hash,
                            }
                            try:
                                on_challenge_created(event_data)
                            except Exception as h:  # pragma: no cover
                                logging.exception("handler error: %s", h)
                        # next chunk
                        slice_start = slice_end + 1
                    # advance cursor after processing up to to_block
                    next_from = to_block + 1
            except Exception as e:  # pragma: no cover
                logging.warning("web3 poll error: %s", e)
            time.sleep(max(1.0, float(self.cfg.poll_seconds)))
