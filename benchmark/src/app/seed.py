"""Seed deterministic records into Aerospike for benchmark runs.

Uses the official client (sync) — seeding speed doesn't matter and we want
zero coupling with the aerospike-py async path under test.
"""

from __future__ import annotations

import argparse
import time

import aerospike

from app.config import NAMESPACE, SET, key_for
from app.model import FEATURE_NAMES


def build_bins(i: int) -> dict[str, object]:
    base: dict[str, object] = {
        "name": f"user_{i}",
        "age": i % 100,
        "score": float(i) * 1.5,
        "tier": ["bronze", "silver", "gold", "platinum"][i % 4],
        "active": (i % 2) == 0,
    }
    # 64 numeric features for DLRM input (S2/S3/S5).
    for j, name in enumerate(FEATURE_NAMES):
        base[name] = float((i * 13 + j) % 1000) / 1000.0
    return base


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18710)
    args = parser.parse_args()

    client = aerospike.client({"hosts": [(args.host, args.port)]}).connect()
    try:
        t0 = time.perf_counter()
        for i in range(args.count):
            client.put(key_for(i), build_bins(i))
            if (i + 1) % 1000 == 0:
                print(f"  seeded {i + 1}/{args.count}")
        dt = time.perf_counter() - t0
        print(f"Done: {args.count} records into {NAMESPACE}/{SET} in {dt:.2f}s ({args.count / dt:.0f} rec/s)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
