import types
from datetime import datetime, timezone, timedelta

from app.services.progress import _progress_wakatime


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_wakatime_summaries_uses_cumulative_total(monkeypatch):
    # Arrange: two-day window
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=1)).timestamp())
    end = int(now.timestamp())

    # Mock responses: include cumulative_total.seconds = 7200 (2 hours)
    payload = {
        "data": [],
        "cumulative_total": {"seconds": 7200.0, "text": "2 hrs"},
        "start": "",
        "end": "",
    }

    def _fake_get(url, headers=None, params=None, timeout=None):
        return _Resp(200, payload)

    monkeypatch.setattr("app.services.progress.requests.get", _fake_get)

    participants = [{"participant_address": "0xAbC"}]
    tokens = {"0xabc": "waka_ABC123"}

    # Act: goal is 2 hours across window
    out = _progress_wakatime(tokens, participants, window=(start, end), goal_type="coding-time", goal_amount=2)

    # Assert: ratio is 1.0
    assert out.get("0xabc") == 1.0


def test_wakatime_summaries_sums_daily_when_no_cumulative(monkeypatch):
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=1)).timestamp())
    end = int(now.timestamp())

    # 1.5h + 0.5h = 2.0h
    payload = {
        "data": [
            {"grand_total": {"total_seconds": 5400}},
            {"grand_total": {"total_seconds": 1800}},
        ],
        # No cumulative_total provided in this payload
    }

    def _fake_get(url, headers=None, params=None, timeout=None):
        return _Resp(200, payload)

    monkeypatch.setattr("app.services.progress.requests.get", _fake_get)

    participants = [{"participant_address": "0x123"}]
    tokens = {"0x123": "waka_XYZ"}

    out = _progress_wakatime(tokens, participants, window=(start, end), goal_type="coding-time", goal_amount=2)

    assert out.get("0x123") == 1.0
