from __future__ import annotations

import argparse
import json
import sys

from app.services import indexer
from app.services import chain_writer
from app.core.config import settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Motify indexer CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("index-challenges", help="Fetch and cache ended challenges")
    p1.add_argument("--limit", type=int, default=1000)
    p1.add_argument("--all", action="store_true", help="Index all challenges (not only ready-to-end)")

    p2 = sub.add_parser("index-details", help="Cache participants for a challenge")
    p2.add_argument("challenge_id", type=int)

    p3 = sub.add_parser("ready", help="List ready challenges from cache")
    p3.add_argument("--limit", type=int, default=200)

    p4 = sub.add_parser("prepare", help="Prepare a progress-based run (fallback to constant ppm)")
    p4.add_argument("challenge_id", type=int)
    p4.add_argument("--default-percent-ppm", type=int, default=None, help="Override fallback percent in PPM (default: settings.DEFAULT_PERCENT_PPM)")

    p6 = sub.add_parser("index-ready-details", help="Cache participants for all ready challenges")
    p6.add_argument("--limit", type=int, default=200)

    p7 = sub.add_parser("declare-results", help="Declare results on-chain (dry-run by default)")
    p7.add_argument("challenge_id", type=int)
    p7.add_argument("--default-percent-ppm", type=int, default=None, help="Fallback percent (PPM) if progress missing; default: settings.DEFAULT_PERCENT_PPM")
    p7.add_argument("--chunk-size", type=int, default=200)
    p7.add_argument("--send", action="store_true", help="Actually broadcast transactions")
    p7.add_argument("--no-prepare", action="store_true", help="Skip prepare_run and assume external item source (not yet supported)")
    p7.add_argument("--artifacts-out", type=str, default=None, help="Write declare artifacts JSON to this path (items, payload, receipts)")

    # Utility: quick diagnostics for ABI/contract/network issues
    sub.add_parser("sanity-check", help="Print web3/contract diagnostics (chainId, code len, ABI path)")

    # Archive and cleanup after a successful on-chain declare
    p8 = sub.add_parser("archive", help="Archive a processed challenge and cleanup cached rows")
    p8.add_argument("challenge_id", type=int)
    p8.add_argument("--rule-json", type=str, default=None, help="JSON string for rule, e.g. '{\"type\":\"progress\"}'")
    p8.add_argument("--tx-hash", dest="tx_hashes", action="append", default=None, help="Tx hash to include in summary; repeatable")
    p8.add_argument("--items-file", type=str, default=None, help="Path to JSON file with finished_items (list)")
    p8.add_argument("--keep-participants", action="store_true", help="Do not delete cached participants rows")
    p8.add_argument("--artifacts-file", type=str, default=None, help="Path to JSON artifacts from declare-results (contains items, receipts, rule)")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "sanity-check":
            # Late-import to avoid overhead when unused
            from app.services.chain_reader import ChainReader
            r = ChainReader.from_settings()
            if not r:
                out = {"ok": False, "error": "Web3 not configured"}
            else:
                out = {"ok": True, **r.sanity()}
            print(json.dumps(out, indent=2))
            return 0
        if args.cmd == "index-challenges":
            out = indexer.fetch_and_cache_ended_challenges(limit=args.limit, only_ready_to_end=(not args.all))
        elif args.cmd == "index-details":
            out = indexer.cache_participants(args.challenge_id)
        elif args.cmd == "ready":
            out = {"data": indexer.list_ready_challenges(limit=args.limit)}
        elif args.cmd == "prepare":
            default_ppm = args.default_percent_ppm if args.default_percent_ppm is not None else settings.DEFAULT_PERCENT_PPM
            out = indexer.prepare_run(args.challenge_id, default_percent_ppm=default_ppm)
        elif args.cmd == "index-ready-details":
            out = indexer.cache_details_for_ready(limit=args.limit)
        elif args.cmd == "declare-results":
            if args.no_prepare:
                raise SystemExit("--no-prepare path not implemented; use default flow that runs prepare first.")
            default_ppm = args.default_percent_ppm if args.default_percent_ppm is not None else settings.DEFAULT_PERCENT_PPM
            preview = indexer.prepare_run(args.challenge_id, default_percent_ppm=default_ppm)
            out = chain_writer.declare_results(
                args.challenge_id,
                preview["items"],
                chunk_size=args.chunk_size,
                send=args.send,
            )
            # Option B: write artifacts file for archival
            if args.artifacts_out:
                art = {
                    "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
                    "challenge_id": args.challenge_id,
                    "rule": preview.get("rule"),
                    "items": list(preview.get("items") or []),
                    "payload": out.get("payload"),
                    "tx_hashes": out.get("tx_hashes"),
                    "receipts": out.get("receipts"),
                    "dry_run": out.get("dry_run", True),
                    "fee_params_preview": out.get("fee_params_preview"),
                    "used_fee_params": out.get("used_fee_params"),
                }
                # Attach batch_no/tx_hash per item if receipts exist (map by chunk index)
                if not art["dry_run"] and art.get("payload") and art.get("tx_hashes"):
                    # Compute chunk sizes to assign batch numbers
                    chunks = art["payload"].get("chunks") or []
                    idx = 0
                    for batch_no, ch in enumerate(chunks):
                        count = len(ch.get("participants") or [])
                        txh = (art.get("tx_hashes") or [None])[batch_no] if batch_no < len(art.get("tx_hashes") or []) else None
                        for k in range(count):
                            if idx < len(art["items"]):
                                art["items"][idx]["batch_no"] = batch_no
                                if txh:
                                    art["items"][idx]["tx_hash"] = txh
                            idx += 1
                with open(args.artifacts_out, "w", encoding="utf-8") as f:
                    json.dump(art, f, indent=2)
        elif args.cmd == "archive":
            import json as _json
            rule = _json.loads(args.rule_json) if args.rule_json else {"type": "manual"}
            finished_items = None
            # If artifacts file is provided, prefer its contents for rule/items/tx hashes
            if args.artifacts_file:
                with open(args.artifacts_file, "r", encoding="utf-8") as f:
                    art = _json.load(f)
                # Use rule from artifacts if not explicitly passed
                if args.rule_json is None and art.get("rule") is not None:
                    rule = art["rule"]
                # Items always come from artifacts when present
                finished_items = art.get("items")
                # Derive summary.tx_hashes from artifacts if not provided
                if args.tx_hashes is None and (art.get("tx_hashes") or art.get("receipts")):
                    txs = art.get("tx_hashes") or []
                    if not txs and art.get("receipts"):
                        txs = [r.get("transactionHash") for r in (art.get("receipts") or []) if r]
                    args.tx_hashes = txs or None
            if args.items_file:
                with open(args.items_file, "r", encoding="utf-8") as f:
                    finished_items = _json.load(f)
            summary = {}
            if args.tx_hashes:
                summary["tx_hashes"] = args.tx_hashes
            out = indexer.archive_and_cleanup(
                args.challenge_id,
                rule=rule,
                summary=summary or None,
                delete_participants=(not args.keep_participants),
                finished_items=finished_items,
            )
        else:
            parser.error("unknown command")
            return 2
        print(json.dumps(out, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e), "type": e.__class__.__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
