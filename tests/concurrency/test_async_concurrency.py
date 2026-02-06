"""Async concurrency stress tests (requires Aerospike server)."""

import asyncio

import pytest

import aerospike_py

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET_NAME = "conc_async"


class TestAsyncConcurrency:
    async def test_100_concurrent_puts(self, async_client):
        """asyncio.gather with 100 concurrent put operations."""

        async def do_put(i):
            key = (NS, SET_NAME, f"aput_{i}")
            await async_client.put(key, {"v": i})

        await asyncio.gather(*(do_put(i) for i in range(100)))

        # Verify and cleanup
        for i in range(100):
            key = (NS, SET_NAME, f"aput_{i}")
            _, _, bins = await async_client.get(key)
            assert bins["v"] == i
            await async_client.remove(key)

    async def test_mixed_operations_concurrent(self, async_client):
        """Concurrent put/get/increment mix."""
        key = (NS, SET_NAME, "amixed")
        await async_client.put(key, {"counter": 0, "data": "init"})

        async def increment_n(n):
            for _ in range(n):
                await async_client.increment(key, "counter", 1)

        async def read_n(n):
            for _ in range(n):
                await async_client.get(key)

        await asyncio.gather(
            increment_n(50),
            read_n(50),
            increment_n(50),
            read_n(50),
        )

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == 100
        await async_client.remove(key)

    async def test_rapid_connect_disconnect(self):
        """Repeated connect/close cycles for stability."""
        for _ in range(10):
            c = aerospike_py.AsyncClient(CONFIG)
            try:
                await c.connect()
            except Exception:
                pytest.skip("Aerospike server not available")
            assert c.is_connected()
            await c.close()
            assert not c.is_connected()

    async def test_semaphore_bounded_concurrency(self, async_client):
        """Semaphore(20) controlling 200 concurrent operations."""
        sem = asyncio.Semaphore(20)

        async def bounded_op(i):
            async with sem:
                key = (NS, SET_NAME, f"asem_{i}")
                await async_client.put(key, {"v": i})
                _, _, bins = await async_client.get(key)
                assert bins["v"] == i
                await async_client.remove(key)

        await asyncio.gather(*(bounded_op(i) for i in range(200)))
