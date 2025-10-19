import requests


def test_health_endpoint(test_api_base_url):
    r = requests.get(test_api_base_url + "/health", timeout=3)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "db" in data
