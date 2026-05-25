"""Shared fixtures for feasibility tests (requires Aerospike server)."""

import os
import socket

import pytest


def _server_available(host: str | None = None, port: int | None = None) -> bool:
    host = host or os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
    port = port if port is not None else int(os.environ.get("AEROSPIKE_PORT", "18710"))

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
