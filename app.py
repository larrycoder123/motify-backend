from flask import Flask, request, jsonify
from datetime import datetime, timezone
from threading import Thread
import time

app = Flask(__name__)

# In-memory store for challenges
challenges = {}
challenge_id_counter = 1


class Challenge:
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
        self.participants = []
        self.completed = False

    def to_dict(self):
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


def monitor_challenges():
    while True:
        now = datetime.now(timezone.utc)
        for challenge in list(challenges.values()):
            if not challenge.completed and challenge.end_date < now:
                challenge.completed = True
                # Placeholder for event (e.g. refund, reward, etc.)
                print(
                    f"Challenge '{challenge.name}' ended! Triggering event...")
        time.sleep(5)


@app.route("/challenges", methods=["POST"])
def create_challenge():
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
    return jsonify([c.to_dict() for c in challenges.values()])


@app.route("/challenges/<int:challenge_id>/join", methods=["POST"])
def join_challenge(challenge_id):
    data = request.get_json()
    user = data.get("user")

    if not user:
        return jsonify({"error": "Missing 'user'"}), 400

    challenge = challenges.get(challenge_id)
    if not challenge:
        return jsonify({"error": "Challenge not found"}), 404

    if user in challenge.participants:
        return jsonify({"message": "User already joined"}), 200

    challenge.participants.append(user)
    return jsonify({"message": f"{user} joined challenge {challenge.name}"}), 200


if __name__ == "__main__":
    # Start background thread for checking ended challenges
    Thread(target=monitor_challenges, daemon=True).start()
    app.run(debug=True)
