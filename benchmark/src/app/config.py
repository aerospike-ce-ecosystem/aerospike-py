"""Runtime config from env vars."""

from __future__ import annotations

import os

NAMESPACE = "test"
SET = "bench"

AEROSPIKE_HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
AEROSPIKE_PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))

# Which client to mount on app startup. The server runs ONE client per process
# to keep the comparison clean — no in-process toggle.
CLIENT_KIND = os.environ.get("CLIENT", "py")  # "py" | "official"


def key_for(i: int) -> tuple[str, str, str]:
    """Deterministic key shared by seed and routes."""
    return (NAMESPACE, SET, f"row_{i:08d}")
