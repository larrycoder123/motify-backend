import argparse
import sys
import time
from pathlib import Path

import requests


def read_env_contract(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("MOTIFY_CONTRACT_ADDRESS="):
                return s.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Watch for listener to activate challenge by metadata hash")
    parser.add_argument("--hash", required=True, help="metadata hash (0x...) to match against description_hash")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--timeout", type=int, default=900, help="Timeout seconds (default 900s)")
    parser.add_argument("--interval", type=float, default=5.0, help="Poll interval seconds (default 5s)")
    args = parser.parse_args()

    env_path = Path(".env")
    contract = read_env_contract(env_path)
    if not contract:
        print("watcher: no MOTIFY_CONTRACT_ADDRESS found in .env", file=sys.stderr)
        sys.exit(2)

    target_hash = (args.hash or "").lower()
    print(f"watcher: watching base={args.base} contract={contract} hash={target_hash}")

    start = time.time()
    last = None
    while time.time() - start < args.timeout:
        try:
            r = requests.get(f"{args.base}/challenges", timeout=10)
            if not r.ok:
                print("watcher: /challenges error", r.status_code, r.text)
                time.sleep(args.interval)
                continue
            items = r.json() or []
            match = [
                c for c in items
                if (c.get("contract_address") or "").lower() == contract.lower()
                and ((c.get("description_hash") or "").lower() == target_hash)
            ]
            if match:
                c = match[0]
                key = (c.get("status"), c.get("on_chain_challenge_id"))
                if key != last:
                    print(
                        "watcher: status=", c.get("status"),
                        " on_chain_id=", c.get("on_chain_challenge_id"),
                        " tx=", c.get("created_tx_hash"),
                        " block=", c.get("created_block_number"),
                        " id=", c.get("id"),
                    )
                    last = key
                if c.get("status") == "active" and c.get("on_chain_challenge_id") is not None:
                    print("watcher: success (challenge activated)")
                    return 0
            else:
                if last is None:
                    print("watcher: pending row not found yet; will retry")
                    last = ("searching", None)
        except Exception as e:
            print("watcher: error:", type(e).__name__, str(e))
        time.sleep(args.interval)

    print("watcher: timeout waiting for activation", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
