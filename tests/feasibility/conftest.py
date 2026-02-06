"""Shared fixtures for feasibility tests (requires Aerospike server)."""

import socket

import pytest


def _server_available(host: str = "127.0.0.1", port: int = 3000) -> bool:
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_aerospike():
    if not _server_available():
        pytest.skip("Aerospike server not available")
