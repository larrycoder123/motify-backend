import os
import time
from threading import Thread

import pytest
import requests
import uvicorn

from app.main import app


@pytest.fixture(scope="session")
def test_api_base_url():
    """Provide a base URL for API tests.
    If API_BASE_URL is set, validate and return it. Otherwise, start a local uvicorn server and return its URL.
    """
    # If an external server is provided, use it and don't start our own
    external = os.getenv("API_BASE_URL")
    if external:
        base = external.rstrip("/")
        print(f"[test_api_base_url] Using external API_BASE_URL: {base}")
        # quick health check
        r = requests.get(base + "/health", timeout=3)
        assert r.status_code == 200
        yield base
        return

    port = int(os.getenv("TEST_API_PORT", "8020"))
    host = os.getenv("TEST_API_HOST", "127.0.0.1")
    print(f"[test_api_base_url] Starting uvicorn on {host}:{port}...")
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://{host}:{port}"
    # Wait for server to be ready
    deadline = time.time() + 25
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(base + "/health", timeout=1.5)
            if r.status_code == 200:
                print("[test_api_base_url] Health check OK.")
                break
        except Exception as e:  # pragma: no cover
            last_err = e
            time.sleep(0.2)
    else:
        raise RuntimeError(f"API server did not start: {last_err}")

    yield base

    # Teardown
    print("[test_api_base_url] Tearing down server...")
    server.should_exit = True
    thread.join(timeout=3)
