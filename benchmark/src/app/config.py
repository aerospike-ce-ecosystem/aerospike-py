"""Runtime config from env vars."""

from __future__ import annotations

import os

NAMESPACE = "test"
SET = "bench"

AEROSPIKE_HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
AEROSPIKE_PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))

# Must match `cluster-name` in scripts/aerospike.template.conf, otherwise the
# client silently connects to whichever Aerospike node happens to answer the
# seed-host cluster-info round-trip.
AEROSPIKE_CLUSTER_NAME = os.environ.get("AEROSPIKE_CLUSTER_NAME", "docker")

# Which client to mount on app startup. The server runs ONE client per process
# to keep the comparison clean — no in-process toggle.
CLIENT_KIND = os.environ.get("CLIENT", "py")  # "py" | "official"

# Optional backpressure cap for aerospike-py AsyncClient. Without this, a
# bursty load can put more in-flight batch_reads than the server pool can
# absorb — the production-benchmark B-environment numbers show this as
# request errors at concurrency=10. Unset by default; set in env to enable.
_max = os.environ.get("AEROSPIKE_MAX_CONCURRENT_OPS")
AEROSPIKE_MAX_CONCURRENT_OPS: int | None = int(_max) if _max else None


def key_for(i: int) -> tuple[str, str, str]:
    """Deterministic key shared by seed and routes."""
    return (NAMESPACE, SET, f"row_{i:08d}")
