"""One-shot seeder — populate Aerospike CE with 9 sets × SEED_KEYS_PER_SET keys.

Run from inside the saturation-app container so AEROSPIKE_HOST=aerospike
resolves on the compose network and cluster-discovery topology is reachable:

  podman exec saturation-app python -m app.seed
"""

from __future__ import annotations

import asyncio
import time

from aerospike_py import AsyncClient

from . import config
from .keys import seed_keys_for_set


async def _put_batch(client: AsyncClient, keys: list, payload: dict) -> None:
    await asyncio.gather(*[client.put(k, payload) for k in keys])


async def main() -> None:
    client = AsyncClient({"hosts": [(config.AEROSPIKE_HOST, config.AEROSPIKE_PORT)]})
    await client.connect()

    payload = {
        "f0": 1.0,
        "f1": "feature-string-value-with-some-length-to-model-real-bins",
        "f2": [0.1, 0.2, 0.3, 0.4, 0.5],
        "f3": 42,
    }

    t0 = time.perf_counter()
    for set_name in config.FV_SET_NAMES:
        keys = seed_keys_for_set(set_name)
        for chunk_start in range(0, len(keys), 200):
            chunk = keys[chunk_start : chunk_start + 200]
            await _put_batch(client, chunk, payload)
        print(f"seeded {set_name}: {len(keys)} keys")
    elapsed = time.perf_counter() - t0
    print(f"done in {elapsed:.1f}s")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
