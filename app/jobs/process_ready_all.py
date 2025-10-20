from __future__ import annotations

import os
import json
from typing import Any, Dict, List

from app.services import indexer
from app.services import chain_writer
from app.services.chain_reader import ChainReader
from app.core.config import settings


def _annotate_items_with_batches(items: List[Dict[str, Any]], payload: Dict[str, Any] | None, tx_hashes: List[str] | None) -> List[Dict[str, Any]]:
    if not items or not payload:
        return items
    chunks = payload.get("chunks") or []
    idx = 0
    for batch_no, ch in enumerate(chunks):
        count = len(ch.get("participants") or [])
        txh = (tx_hashes or [None])[batch_no] if tx_hashes and batch_no < len(tx_hashes) else None
        for _ in range(count):
            if idx < len(items):
                items[idx]["batch_no"] = batch_no
                if txh:
                    items[idx]["tx_hash"] = txh
            idx += 1
    return items


def main() -> int:
    # Controls
    def _int_env(name: str, default: int) -> int:
        val = os.getenv(name)
        if val is None:
            return default
        sval = str(val).strip()
        if sval == "":
            return default
        try:
            return int(sval)
        except Exception:
            return default

    default_percent_ppm = _int_env("DEFAULT_PERCENT_PPM", 0)
    chunk_size = _int_env("CHUNK_SIZE", 200)
    # Default to dry-run unless explicitly enabled.
    # Accept both SEND_TX and TX_SEND env flags for convenience.
    send_flag = os.getenv("SEND_TX") or os.getenv("TX_SEND") or "false"
    send = str(send_flag).lower() in {"1", "true", "yes"}

    # 1) Refresh cache from chain (ended & not-finalized only)
    ref = indexer.fetch_and_cache_ended_challenges(limit=1000, only_ready_to_end=True, exclude_finished=True)
    # 2) Ensure participants cached for ready challenges
    det = indexer.cache_details_for_ready(limit=200)
    # 3) List ready challenges
    ready = indexer.list_ready_challenges(limit=200)
    # Reader for on-chain reconciliation
    reader = ChainReader.from_settings()

    processed: List[Dict[str, Any]] = []
    for row in ready:
        cid = int(row.get("challenge_id"))
        try:
            # Prepare items (for all cached participants)
            preview = indexer.prepare_run(cid, default_percent_ppm=default_percent_ppm)
            all_items = list(preview.get("items") or [])

            # If we can read on-chain state, restrict declare to only pending participants
            pending_addrs_lc: set[str] = set()
            declared_onchain: List[Dict[str, Any]] = []
            if reader is not None:
                detail = reader.get_challenge_detail(cid)
                parts = detail.get("participants") or []
                for p in parts:
                    addr = str(p.get("participant_address")).lower()
                    if p.get("result_declared"):
                        declared_onchain.append(p)
                    else:
                        pending_addrs_lc.add(addr)

            # Filter items to only pending
            items = [it for it in all_items if str(it.get("user")).lower() in pending_addrs_lc] if pending_addrs_lc else list(all_items)

            declared_now = False
            dec: Dict[str, Any] = {"dry_run": True, "tx_hashes": [], "used_fee_params": [], "payload": {"challenge_id": cid, "chunks": []}}
            archived = None

            try:
                # If there are pending items and sending is enabled, declare them; otherwise skip sending
                if items and send:
                    dec = chain_writer.declare_results(cid, items, chunk_size=chunk_size, send=True)
                    declared_now = not dec.get("dry_run", True)
            except Exception as e:
                msg = str(e)
                # Reconcile path on already-declared revert: refresh on-chain state
                if "Result already declared for participant" in msg:
                    if reader is not None:
                        detail2 = reader.get_challenge_detail(cid)
                        parts2 = detail2.get("participants") or []
                        # Recompute pending set
                        pending2 = [p for p in parts2 if not p.get("result_declared")]
                        if not pending2 and send:
                            # Everyone already declared on-chain -> proceed to archive from chain state
                            declared_now = False
                        else:
                            # Still pending exist; bubble up to retry later
                            raise
                else:
                    # Unknown error; bubble up
                    raise

            # Build finished_items for archival:
            # - include newly-declared items (if any)
            # - include already-declared from on-chain (if available)
            items_annot = _annotate_items_with_batches(items, dec.get("payload"), dec.get("tx_hashes"))
            finished_items: List[Dict[str, Any]] = []
            finished_items.extend(items_annot)

            # Add on-chain declared items (avoid duplicates)
            if declared_onchain:
                seen_lc = {str(it.get("user")).lower() for it in finished_items}
                for p in declared_onchain:
                    addr = str(p.get("participant_address"))
                    if addr.lower() in seen_lc:
                        continue
                    ppm = int(p.get("refund_percentage") or 0) * 100  # bps -> ppm
                    finished_items.append({
                        "user": addr,
                        "stake_minor_units": int(p.get("amount") or 0),
                        "percent_ppm": ppm,
                        "progress_ratio": None,
                    })

            # Decide whether to archive:
            # - If we sent txs (declared_now) -> archive
            # - Or if there is nothing pending (i.e., all were already declared on-chain) and sending is enabled -> archive without txs
            no_pending = (not pending_addrs_lc) or (pending_addrs_lc and not items)
            allow_archive = send and (declared_now or no_pending)
            if allow_archive:
                archived = indexer.archive_and_cleanup(
                    cid,
                    rule=preview.get("rule") or {"type": "progress", "fallback_percent_ppm": default_percent_ppm},
                    summary={"tx_hashes": dec.get("tx_hashes") or []},
                    delete_participants=True,
                    finished_items=finished_items if finished_items else None,
                )

            processed.append({
                "challenge_id": cid,
                "declare": {k: v for k, v in dec.items() if k in ("dry_run", "tx_hashes", "used_fee_params", "fee_params_preview", "payload")},
                "archived": archived,
            })
        except Exception as e:
            processed.append({"challenge_id": cid, "error": str(e)})

    print(json.dumps({
        "refresh": ref,
        "details": det,
        "ready_count": len(ready),
        "processed": processed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
