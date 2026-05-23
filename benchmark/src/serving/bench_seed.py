"""Seed Aerospike with synthetic feature rows for `/bench/*` endpoints."""

from __future__ import annotations

import os
import sys

import numpy as np

import aerospike_py

HOST = os.environ.get("AEROSPIKE_HOST", "127.0.0.1")
PORT = int(os.environ.get("AEROSPIKE_PORT", "18710"))
NS = "test"
SET = "bench_serving"
N = int(os.environ.get("BENCH_SEED_N", "2000"))
N_FEATURES = int(os.environ.get("BENCH_N_FEATURES", "64"))


def main() -> None:
    client = aerospike_py.client({"hosts": [(HOST, PORT)], "cluster_name": "docker"}).connect()
    try:
        rng = np.random.default_rng(seed=42)
        print(f"seeding ns={NS} set={SET} rows={N} features={N_FEATURES} -> {HOST}:{PORT}")
        for i in range(N):
            key = (NS, SET, f"row_{i}")
            bins = {f"f{j}": float(rng.random()) for j in range(N_FEATURES)}
            client.put(key, bins)
            if (i + 1) % 500 == 0:
                print(f"  {i + 1}/{N}")
        print("done.")
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
