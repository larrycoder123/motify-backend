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
        with Path(abi_path).open("r", encoding="utf-8") as f:
            abi = json.load(f)
        self.contract: Contract = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

    @classmethod
    def from_settings(cls) -> Optional["ChainReader"]:
        if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
            return None
        return cls(settings.WEB3_RPC_URL, settings.MOTIFY_CONTRACT_ADDRESS, settings.MOTIFY_CONTRACT_ABI_PATH)

    def get_all_challenges(self, limit: int = 1000) -> List[Dict[str, Any]]:
        res = self.contract.functions.getAllChallenges(limit).call()
        parsed: List[Dict[str, Any]] = []
        for item in res:
            parsed.append({
                "challenge_id": int(item[0]),
                "recipient": item[1],
                "start_time": int(item[2]),
                "end_time": int(item[3]),
                "is_private": bool(item[4]),
                "api_type": item[5],
                "goal_type": item[6],
                "goal_amount": int(item[7]),
                "description": item[8],
                "total_donation_amount": int(item[9]),
                "results_finalized": bool(item[10]),
                "participant_count": int(item[11]),
            })
        return parsed

    def get_challenge_detail(self, challenge_id: int) -> Dict[str, Any]:
        d = self.contract.functions.getChallengeById(challenge_id).call()
        # d schema: (challengeId, recipient, startTime, endTime, isPrivate, apiType, goalType, goalAmount, description, totalDonationAmount, resultsFinalized, participants[])
        participants = []
        for p in d[11]:
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
            "api_type": d[5],
            "goal_type": d[6],
            "goal_amount": int(d[7]),
            "description": d[8],
            "total_donation_amount": int(d[9]),
            "results_finalized": bool(d[10]),
            "participants": participants,
        }
