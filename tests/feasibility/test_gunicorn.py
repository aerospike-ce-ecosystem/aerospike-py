"""Gunicorn WSGI multi-worker compatibility test (requires Aerospike server)."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("gunicorn")

# ---------------------------------------------------------------------------
# Inline WSGI application (written to a temp file so gunicorn can import it)
# ---------------------------------------------------------------------------
WSGI_APP_CODE = '''
import json
import os

import aerospike_py

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET_NAME = "feasibility_gunicorn"

_client = None


def _get_client():
    """Lazy per-worker client — safe after fork."""
    global _client
    if _client is None:
        _client = aerospike_py.client(CONFIG).connect()
    return _client


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/health":
        body = json.dumps({"status": "ok", "pid": os.getpid()}).encode()
        start_response("200 OK", [("Content-Type", "application/json")])
        return [body]

    if path.startswith("/kv/"):
        key_name = path[len("/kv/"):]
        c = _get_client()
        if method == "PUT":
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            raw = environ["wsgi.input"].read(length) if length else b"{}"
            data = json.loads(raw) if raw else {}
            value = data.get("value", 0)
            c.put((NS, SET_NAME, key_name), {"v": value})
            body = json.dumps({"key": key_name, "value": value, "pid": os.getpid()}).encode()
            start_response("200 OK", [("Content-Type", "application/json")])
            return [body]
        if method == "GET":
            _, _, bins = c.get((NS, SET_NAME, key_name))
            body = json.dumps({"key": key_name, "bins": bins, "pid": os.getpid()}).encode()
            start_response("200 OK", [("Content-Type", "application/json")])
            return [body]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]
'''


def _free_port() -> int:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"Gunicorn on port {port} did not start within {timeout}s")


@pytest.fixture(scope="module")
def gunicorn_url():
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        app_path = os.path.join(tmpdir, "wsgi_app.py")
        with open(app_path, "w") as f:
            f.write(WSGI_APP_CODE)

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gunicorn",
                "wsgi_app:application",
                "-b",
                f"127.0.0.1:{port}",
                "-w",
                "4",
                "--timeout",
                "30",
            ],
            cwd=tmpdir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_server(port)
            yield f"http://127.0.0.1:{port}"
        finally:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)


class TestGunicornFeasibility:
    def test_health_from_multiple_workers(self, gunicorn_url):
        """Send requests over separate connections to distribute across workers."""
        pids = set()
        for _ in range(20):
            # Each request uses a fresh connection (no keep-alive)
            # so gunicorn can round-robin across workers
            r = httpx.get(f"{gunicorn_url}/health")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            pids.add(body["pid"])

        assert len(pids) >= 2, f"Expected >= 2 worker PIDs, got {pids}"

    def test_put_get_across_workers(self, gunicorn_url):
        """Put from one request, get from subsequent requests — data shared via server."""
        r = httpx.put(
            f"{gunicorn_url}/kv/gtest1",
            content=json.dumps({"value": 999}),
        )
        assert r.status_code == 200

        # Multiple gets over separate connections to hit different workers
        for _ in range(10):
            r = httpx.get(f"{gunicorn_url}/kv/gtest1")
            assert r.status_code == 200
            assert r.json()["bins"]["v"] == 999
