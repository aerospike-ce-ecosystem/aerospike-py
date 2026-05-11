"""Runtime configuration via environment variables.

All knobs are read once at import time and exposed as module-level constants
to keep the FastAPI hot path branchless.
"""

from __future__ import annotations

import os

# Aerospike connection
AEROSPIKE_HOST: str = os.getenv("AEROSPIKE_HOST", "host.containers.internal")
AEROSPIKE_PORT: int = int(os.getenv("AEROSPIKE_PORT", "18710"))
AEROSPIKE_NAMESPACE: str = os.getenv("AEROSPIKE_NAMESPACE", "test")

# Workload shape — matches issue #347 production env
NUM_FEATURE_VIEWS: int = int(os.getenv("NUM_FEATURE_VIEWS", "9"))
KEYS_PER_FV: int = int(os.getenv("KEYS_PER_FV", "80"))
SEED_KEYS_PER_SET: int = int(os.getenv("SEED_KEYS_PER_SET", "1000"))
FV_SET_NAMES: list[str] = [f"fv_{i}" for i in range(NUM_FEATURE_VIEWS)]

# Which client to exercise — selected via env, NOT request param,
# so a single deployment compares one client at a time (avoids client
# selection branch in the hot path).
CLIENT_KIND: str = os.getenv("CLIENT_KIND", "aerospike-py")  # 'aerospike-py' | 'legacy'

# CPU-bound co-resident workload to model DLRM-style GIL contention.
# Without this, GIL pressure understates the production environment
# (issue #347 prod runs DLRM PyTorch ~50-100 ms per request alongside).
#
# We target a burn duration (CPU_BOUND_BURN_MS) rather than a fixed
# matrix size — easier to tune and translates across hardware. The burn
# uses NumPy matmul (some GIL release via BLAS) plus Python-level
# reduction (forces GIL hold) so it competes with aerospike-py's tokio
# worker GIL acquisitions.
CPU_BOUND_BURN_MS: int = int(os.getenv("CPU_BOUND_BURN_MS", "0"))  # 0 = legacy N*N path
CPU_BOUND_MATMUL_N: int = int(os.getenv("CPU_BOUND_MATMUL_N", "64"))
CPU_BOUND_ENABLED: bool = os.getenv("CPU_BOUND_ENABLED", "1") in ("1", "true", "yes")
CPU_BOUND_TORCH: bool = os.getenv("CPU_BOUND_TORCH", "0") in ("1", "true", "yes")

# Stage profiling — always on for the reproducer
os.environ.setdefault("AEROSPIKE_PY_INTERNAL_METRICS", "1")
