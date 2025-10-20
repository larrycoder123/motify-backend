from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Dict, Optional

from web3 import Web3
from web3.contract import Contract

from app.core.config import settings


class ChainReader:
    def __init__(self, rpc_url: str, contract_address: str, abi_path: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        # Resolve ABI path to avoid CWD issues and support artifact objects
        self.abi_path = str(Path(abi_path).resolve())
        with Path(self.abi_path).open("r", encoding="utf-8") as f:
            raw = json.load(f)
        abi = raw.get("abi") if isinstance(raw, dict) and "abi" in raw else raw
        if not isinstance(abi, list):
            raise RuntimeError("Invalid ABI JSON: expected list or artifact with 'abi' key")
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract: Contract = self.w3.eth.contract(address=self.contract_address, abi=abi)

    @classmethod
    def from_settings(cls) -> Optional["ChainReader"]:
        if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
            return None
        return cls(settings.WEB3_RPC_URL, settings.MOTIFY_CONTRACT_ADDRESS, settings.MOTIFY_CONTRACT_ABI_PATH)

    def get_all_challenges(self, limit: int = 1000) -> List[Dict[str, Any]]:
        try:
            res = self.contract.functions.getAllChallenges(limit).call()
        except Exception as e:
            # Provide actionable diagnostics for common misconfigurations
            try:
                chain_id = self.w3.eth.chain_id
            except Exception:
                chain_id = None
            try:
                code = self.w3.eth.get_code(self.contract_address)
                code_len = len(code or b"")
            except Exception:
                code_len = None
            diag = {
                "error": str(e),
                "chain_id": chain_id,
                "contract_address": self.contract_address,
                "contract_code_len": code_len,
                "abi_path": self.abi_path,
            }
            raise RuntimeError(f"getAllChallenges call failed; diagnostics: {diag}")
        parsed: List[Dict[str, Any]] = []
        for item in res:
            # Support both old and new ABI layouts
            # Old: [id,recipient,start,end,isPrivate,apiType,goalType,goalAmount,description,totalDonation,resultsFinalized,participantCount]
            # New: [id,recipient,start,end,isPrivate,name,apiType,goalType,goalAmount,description,totalDonation,resultsFinalized,participantCount]
            length = len(item)
            is_new = length >= 13
            name = item[5] if is_new else ""
            api_type = item[6] if is_new else item[5]
            goal_type = item[7] if is_new else item[6]
            goal_amount = item[8] if is_new else item[7]
            description = item[9] if is_new else item[8]
            total_donation = item[10] if is_new else item[9]
            results_finalized = item[11] if is_new else item[10]
            participant_count = item[12] if is_new else item[11]

            parsed.append({
                "challenge_id": int(item[0]),
                "recipient": item[1],
                "start_time": int(item[2]),
                "end_time": int(item[3]),
                "is_private": bool(item[4]),
                "name": name,
                "api_type": api_type,
                "goal_type": goal_type,
                "goal_amount": int(goal_amount),
                "description": description,
                "total_donation_amount": int(total_donation),
                "results_finalized": bool(results_finalized),
                "participant_count": int(participant_count),
            })
        return parsed

    def get_challenge_detail(self, challenge_id: int) -> Dict[str, Any]:
        try:
            d = self.contract.functions.getChallengeById(challenge_id).call()
        except Exception as e:
            try:
                chain_id = self.w3.eth.chain_id
            except Exception:
                chain_id = None
            try:
                code = self.w3.eth.get_code(self.contract_address)
                code_len = len(code or b"")
            except Exception:
                code_len = None
            diag = {
                "error": str(e),
                "chain_id": chain_id,
                "contract_address": self.contract_address,
                "contract_code_len": code_len,
                "abi_path": self.abi_path,
                "challenge_id": int(challenge_id),
            }
            raise RuntimeError(f"getChallengeById call failed; diagnostics: {diag}")
        # Old: (id,recipient,start,end,isPrivate,apiType,goalType,goalAmount,description,totalDonation,resultsFinalized,participants[])
        # New: (id,recipient,start,end,isPrivate,name,apiType,goalType,goalAmount,description,totalDonation,resultsFinalized,participants[])
        length = len(d)
        is_new = length >= 13
        name = d[5] if is_new else ""
        api_type = d[6] if is_new else d[5]
        goal_type = d[7] if is_new else d[6]
        goal_amount = d[8] if is_new else d[7]
        description = d[9] if is_new else d[8]
        total_donation = d[10] if is_new else d[9]
        results_finalized = d[11] if is_new else d[10]
        participants_idx = 12 if is_new else 11

        participants = []
        for p in d[participants_idx]:
            # Old: (participantAddress, amount, refundPercentage, resultDeclared)
            # New: (participantAddress, initialAmount, amount, refundPercentage, resultDeclared)
            if len(p) >= 5:
                participants.append({
                    "participant_address": p[0],
                    "initial_amount": int(p[1]),
                    "amount": int(p[2]),
                    "refund_percentage": int(p[3]),
                    "result_declared": bool(p[4]),
                })
            else:
                participants.append({
                    "participant_address": p[0],
                    "amount": int(p[1]),
                    "refund_percentage": int(p[2]),
                    "result_declared": bool(p[3]),
                })

        return {
            "challenge_id": int(d[0]),
            "recipient": d[1],
            "start_time": int(d[2]),
            "end_time": int(d[3]),
            "is_private": bool(d[4]),
            "name": name,
            "api_type": api_type,
            "goal_type": goal_type,
            "goal_amount": int(goal_amount),
            "description": description,
            "total_donation_amount": int(total_donation),
            "results_finalized": bool(results_finalized),
            "participants": participants,
        }

    def sanity(self) -> Dict[str, Any]:
        """Return basic diagnostics for easier troubleshooting."""
        try:
            chain_id = self.w3.eth.chain_id
        except Exception:
            chain_id = None
        try:
            code = self.w3.eth.get_code(self.contract_address)
            code_len = len(code or b"")
        except Exception:
            code_len = None
        return {
            "rpc_url": settings.WEB3_RPC_URL,
            "contract_address": self.contract_address,
            "chain_id": chain_id,
            "contract_code_len": code_len,
            "abi_path": self.abi_path,
        }
