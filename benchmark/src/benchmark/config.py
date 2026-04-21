"""Aerospike cluster configuration and benchmark defaults."""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Cluster topology — 8 node cluster
# ---------------------------------------------------------------------------

_DEFAULT_HOSTS = [
    ("maiasp025-sa", 3000),
    ("maiasp026-sa", 3000),
    ("maiasp027-sa", 3000),
    ("maiasp028-sa", 3000),
    ("maiasp029-sa", 3000),
    ("maiasp030-sa", 3000),
    ("maiasp031-sa", 3000),
    ("maiasp032-sa", 3000),
]

_DEFAULT_NAMESPACE = "aidev"


def get_hosts() -> list[tuple[str, int]]:
    """Return cluster hosts, respecting AEROSPIKE_HOSTS override.

    Format: ``host1:port1,host2:port2,...``
    """
    env = os.environ.get("AEROSPIKE_HOSTS")
    if not env:
        return _DEFAULT_HOSTS
    pairs: list[tuple[str, int]] = []
    for entry in env.split(","):
        entry = entry.strip()
        if ":" in entry:
            host, port_str = entry.rsplit(":", 1)
            pairs.append((host, int(port_str)))
        else:
            pairs.append((entry, 3000))
    return pairs


def get_namespace() -> str:
    """Return namespace, respecting AEROSPIKE_NAMESPACE override."""
    return os.environ.get("AEROSPIKE_NAMESPACE", _DEFAULT_NAMESPACE)


# ---------------------------------------------------------------------------
# Set definitions — set_name to primary-key field mapping
# ---------------------------------------------------------------------------

SET_KEY_FIELD: dict[str, str] = {
    "set_1": "adId",
    "set_2": "adGroupId",
    "set_3": "campaignId",
    "set_4": "adId_channelId",
    "set_5": "adGroupId_channelId",
    "set_6": "campaignId_channelId",
    "set_7": "nvmid",
    "set_8": "userId",
    "set_9": "nv_mid",
}

ALL_SETS = list(SET_KEY_FIELD.keys())

# ---------------------------------------------------------------------------
# Benchmark defaults
# ---------------------------------------------------------------------------

DEFAULT_BATCH_SIZES = [50, 100, 200, 500]
DEFAULT_ITERATIONS = 100
DEFAULT_WARMUP = 10
