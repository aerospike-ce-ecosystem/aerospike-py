"""Shared fixtures for feasibility tests (requires Aerospike server)."""

import os
import socket

import pytest


def _server_available(host: str = "127.0.0.1", port: int = 18710) -> bool:
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except OSError:
        return False


def _server_endpoint() -> tuple[str, int]:
    return (
        os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
        int(os.environ.get("AEROSPIKE_PORT", "18710")),
    )


@pytest.fixture(scope="session", autouse=True)
def require_aerospike():
    host, port = _server_endpoint()
    if not _server_available(host, port):
        pytest.skip(f"Aerospike server not available at {host}:{port}")
