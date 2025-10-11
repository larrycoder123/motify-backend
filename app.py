from flask import Flask, request, jsonify
from datetime import datetime, timezone
from threading import Thread
import time
import requests

app = Flask(__name__)

# In-memory store for challenges
challenges = {}
challenge_id_counter = 1

# n8n webhook URL
N8N_WEBHOOK_URL = "https://larrycoder123.app.n8n.cloud/webhook/fetch-fit"


class Challenge:
    """
    Represents a challenge with basic details and participants.
    """

    def __init__(self, name, description, start_date, end_date, contract_address, amount_usd, goal):
        global challenge_id_counter
        self.id = challenge_id_counter
        challenge_id_counter += 1

        self.name = name
        self.description = description
        self.start_date = datetime.fromisoformat(start_date)
        self.end_date = datetime.fromisoformat(end_date)
        self.contract_address = contract_address
        self.amount_usd = amount_usd
        self.goal = goal
        self.participants = []  # list of wallet addresses
        self.completed = False

    def to_dict(self):
        """
        Convert the Challenge object to a dictionary for JSON responses.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "contract_address": self.contract_address,
            "amount_usd": self.amount_usd,
            "goal": self.goal,
            "participants": self.participants,
            "completed": self.completed
        }


def call_n8n_api(wallet_address, start_date, end_date, goal):
    """
    Send a POST request to the n8n webhook and return the response JSON.
    """
    payload = {
        "walletAddress": wallet_address,
        "startDate": start_date,
        "endDate": end_date,
        "goal": goal
    }
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error calling n8n API: {e}")
        return None


def monitor_challenges():
    """
    Background task that checks if challenges have ended and triggers n8n.
    """
    while True:
        now = datetime.now(timezone.utc)
        for challenge in list(challenges.values()):
            if not challenge.completed and challenge.end_date < now:
                challenge.completed = True

                for wallet in challenge.participants:
                    result = call_n8n_api(
                        wallet_address=wallet,
                        start_date=challenge.start_date.date().isoformat(),
                        end_date=challenge.end_date.date().isoformat(),
                        goal=challenge.goal
                    )
                    if result is not None:
                        print(f"[n8n RESPONSE] {wallet}: {result}")
                    else:
                        print(f"[n8n ERROR] Failed to fetch data for {wallet}")
        time.sleep(5)


@app.route("/challenges", methods=["POST"])
def create_challenge():
    """
    Create a new challenge and store it in memory.
    """
    data = request.get_json()
    required_fields = ["name", "description", "start_date",
                       "end_date", "contract_address", "amount_usd", "goal"]

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    challenge = Challenge(
        name=data["name"],
        description=data["description"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        contract_address=data["contract_address"],
        amount_usd=data["amount_usd"],
        goal=data["goal"]
    )

    challenges[challenge.id] = challenge
    return jsonify(challenge.to_dict()), 201


@app.route("/challenges", methods=["GET"])
def get_challenges():
    """
    Return all challenges currently stored in memory.
    """
    return jsonify([c.to_dict() for c in challenges.values()])


@app.route("/challenges/<int:challenge_id>/join", methods=["POST"])
def join_challenge(challenge_id):
    """
    Allow a user to join a specific challenge.
    """
    data = request.get_json()
    wallet = data.get("walletAddress")

    if not wallet:
        return jsonify({"error": "Missing 'walletAddress'"}), 400

    challenge = challenges.get(challenge_id)
    if not challenge:
        return jsonify({"error": "Challenge not found"}), 404

    if wallet in challenge.participants:
        return jsonify({"message": "Wallet already joined"}), 200

    challenge.participants.append(wallet)
    return jsonify({"message": f"Wallet {wallet} joined challenge {challenge.name}"}), 200


@app.route("/challenges/<int:challenge_id>/progress", methods=["POST"])
def get_progress(challenge_id):
    """
    Fetch current progress for ONE wallet address in a given challenge.
    """
    data = request.get_json()
    wallet = data.get("walletAddress")

    if not wallet:
        return jsonify({"error": "Missing 'walletAddress'"}), 400

    challenge = challenges.get(challenge_id)
    if not challenge:
        return jsonify({"error": "Challenge not found"}), 404

    if wallet not in challenge.participants:
        return jsonify({"error": "Wallet not part of this challenge"}), 403

    result = call_n8n_api(
        wallet_address=wallet,
        start_date=challenge.start_date.date().isoformat(),
        end_date=challenge.end_date.date().isoformat(),
        goal=challenge.goal
    )

    if result is None:
        return jsonify({"error": "Failed to fetch data from n8n"}), 502

    return jsonify(result), 200


if __name__ == "__main__":
    # Start background thread for checking ended challenges
    Thread(target=monitor_challenges, daemon=True).start()
    app.run(debug=True)
