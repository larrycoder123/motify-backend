from __future__ import annotations

import argparse
import json
import sys

from app.services import indexer
from app.services import chain_writer


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
    p4.add_argument("--default-percent-ppm", type=int, default=0)

    p6 = sub.add_parser("index-ready-details", help="Cache participants for all ready challenges")
    p6.add_argument("--limit", type=int, default=200)

    p7 = sub.add_parser("declare-results", help="Declare results on-chain (dry-run by default)")
    p7.add_argument("challenge_id", type=int)
    p7.add_argument("--default-percent-ppm", type=int, default=0, help="Fallback percent if progress missing")
    p7.add_argument("--chunk-size", type=int, default=200)
    p7.add_argument("--send", action="store_true", help="Actually broadcast transactions")
    p7.add_argument("--no-prepare", action="store_true", help="Skip prepare_run and assume external item source (not yet supported)")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "index-challenges":
            out = indexer.fetch_and_cache_ended_challenges(limit=args.limit, only_ready_to_end=(not args.all))
        elif args.cmd == "index-details":
            out = indexer.cache_participants(args.challenge_id)
        elif args.cmd == "ready":
            out = {"data": indexer.list_ready_challenges(limit=args.limit)}
        elif args.cmd == "prepare":
            out = indexer.prepare_run(args.challenge_id, default_percent_ppm=args.default_percent_ppm)
        elif args.cmd == "index-ready-details":
            out = indexer.cache_details_for_ready(limit=args.limit)
        elif args.cmd == "declare-results":
            if args.no_prepare:
                raise SystemExit("--no-prepare path not implemented; use default flow that runs prepare first.")
            preview = indexer.prepare_run(args.challenge_id, default_percent_ppm=args.default_percent_ppm)
            out = chain_writer.declare_results(
                args.challenge_id,
                preview["items"],
                chunk_size=args.chunk_size,
                send=args.send,
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
