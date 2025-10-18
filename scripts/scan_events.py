import argparse
import json
import sys
from pathlib import Path


def read_env(key: str) -> str | None:
    try:
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() == key:
                return v.strip()
    except Exception:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Scan recent ChallengeCreated events from contract")
    parser.add_argument("--from-block", type=int, default=None, help="Start block (inclusive). Defaults to latest-2000")
    parser.add_argument("--to-block", type=int, default=None, help="End block (inclusive). Defaults to latest-2 (confirmations)")
    parser.add_argument("--confirmations", type=int, default=2, help="Confirmations to wait for latest tip")
    parser.add_argument("--limit", type=int, default=50, help="Max events to print")
    args = parser.parse_args()

    try:
        from web3 import Web3
    except Exception:
        print("web3 is not installed. Please pip install -r requirements.txt", file=sys.stderr)
        return 2

    rpc = read_env("WEB3_RPC_URL")
    addr = read_env("MOTIFY_CONTRACT_ADDRESS")
    abi_path = read_env("MOTIFY_CONTRACT_ABI_PATH") or "./abi/Motify.json"
    if not rpc or not addr:
        print("Missing WEB3_RPC_URL or MOTIFY_CONTRACT_ADDRESS in .env", file=sys.stderr)
        return 2

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
    if not w3.is_connected():
        print("Failed to connect to RPC", file=sys.stderr)
        return 3

    abi = json.loads(Path(abi_path).read_text(encoding="utf-8"))
    contract = w3.eth.contract(address=w3.to_checksum_address(addr), abi=abi)
    event_cls = getattr(contract.events, "ChallengeCreated")

    latest = w3.eth.block_number
    to_block = args.to_block if args.to_block is not None else max(0, latest - max(0, int(args.confirmations)))
    from_block = args.from_block if args.from_block is not None else max(0, to_block - 2000)

    print(f"Scanning {addr} blocks [{from_block}, {to_block}] on {rpc}")
    logs = event_cls.get_logs(from_block=from_block, to_block=to_block)
    print(f"Found {len(logs)} ChallengeCreated events")
    count = 0
    for log in logs:
        if hasattr(log, "args"):
            argsd = dict(getattr(log, "args") or {})
            bn = getattr(log, "blockNumber", None)
            th = getattr(log, "transactionHash", None)
        else:
            argsd = (log.get("args") if isinstance(log, dict) else {}) or {}
            bn = log.get("blockNumber")
            th = log.get("transactionHash")
        ch_id = int(argsd.get("challengeId"))
        creator = str(argsd.get("creator"))
        recipient = str(argsd.get("recipient"))
        end_time = int(argsd.get("endTime"))
        is_private = bool(argsd.get("isPrivate"))
        mhash = argsd.get("metadataHash")
        try:
            mhash_hex = mhash.hex() if hasattr(mhash, "hex") else str(mhash)
        except Exception:
            mhash_hex = str(mhash)
        txh = th.hex() if hasattr(th, "hex") else str(th)
        print(f"- block={bn} tx={txh} id={ch_id} creator={creator} priv={is_private} end={end_time} metadataHash={mhash_hex}")
        count += 1
        if count >= args.limit:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
