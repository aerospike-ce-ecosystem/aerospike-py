"""Environment-based configuration for the serving app."""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Aerospike cluster
# ---------------------------------------------------------------------------
_DEFAULT_HOSTS = (
    "maiasp025-sa:3000,maiasp026-sa:3000,maiasp027-sa:3000,maiasp028-sa:3000,"
    "maiasp029-sa:3000,maiasp030-sa:3000,maiasp031-sa:3000,maiasp032-sa:3000"
)

AEROSPIKE_HOSTS: list[tuple[str, int]] = []
for pair in os.environ.get("AEROSPIKE_HOSTS", _DEFAULT_HOSTS).split(","):
    host, _, port = pair.strip().partition(":")
    AEROSPIKE_HOSTS.append((host, int(port) if port else 3000))

AEROSPIKE_NAMESPACE: str = os.environ.get("AEROSPIKE_NAMESPACE", "aidev")

# ---------------------------------------------------------------------------
# Thread / concurrency
# ---------------------------------------------------------------------------
THREAD_POOL_SIZE: int = int(os.environ.get("THREAD_POOL_SIZE", "16"))
MAX_CONCURRENT_OPS: int = int(os.environ.get("MAX_CONCURRENT_OPS", "512"))

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
OTEL_ENABLED: bool = os.environ.get("OTEL_SDK_DISABLED", "").lower() != "true"
NELO_ENABLED: bool = os.environ.get("NELO_ENABLED", "true").lower() == "true"
METRICS_PORT: int = int(os.environ.get("METRICS_PORT", "9464"))
