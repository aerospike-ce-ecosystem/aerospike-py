"""Async concurrency stress tests (requires Aerospike server)."""

import asyncio

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG

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
            c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
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

    async def test_50_concurrent_coroutines(self, async_client):
        """50+ coroutines accessing the client simultaneously."""

        async def crud_cycle(i):
            key = (NS, SET_NAME, f"a50_{i}")
            await async_client.put(key, {"v": i, "data": f"value_{i}"})
            record = await async_client.get(key)
            assert record.bins["v"] == i
            await async_client.remove(key)

        await asyncio.gather(*(crud_cycle(i) for i in range(50)))

    async def test_concurrent_batch_read_async(self, async_client):
        """Multiple concurrent batch_read calls from coroutines."""
        keys = [(NS, SET_NAME, f"abr_{i}") for i in range(30)]
        await asyncio.gather(*(async_client.put(k, {"v": int(k[2].split("_")[1])}) for k in keys))

        async def batch_read_task():
            result = await async_client.batch_read(keys, bins=["v"])
            assert len(result.batch_records) == 30

        await asyncio.gather(*(batch_read_task() for _ in range(4)))

        await asyncio.gather(*(async_client.remove(k) for k in keys))

    async def test_concurrent_batch_operate_async(self, async_client):
        """Multiple concurrent batch_operate from coroutines."""
        import aerospike_py

        keys = [(NS, SET_NAME, f"abo_{i}") for i in range(20)]
        await asyncio.gather(*(async_client.put(k, {"counter": 0}) for k in keys))

        ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1}]

        await asyncio.gather(*(async_client.batch_operate(keys, ops) for _ in range(4)))

        for k in keys:
            record = await async_client.get(k)
            assert record.bins["counter"] == 4
            await async_client.remove(k)

    async def test_concurrent_error_paths_async(self, async_client):
        """Multiple coroutines hitting RecordNotFound simultaneously."""
        import aerospike_py

        results = []

        async def read_missing(i):
            key = (NS, SET_NAME, f"amissing_{i}")
            try:
                await async_client.get(key)
                return False  # should not reach here
            except aerospike_py.RecordNotFound:
                return True

        results = await asyncio.gather(*(read_missing(i) for i in range(20)))
        assert all(results), "Not all coroutines got RecordNotFound"

    async def test_concurrent_numpy_batch_read_async(self, async_client):
        """Concurrent numpy batch_read from coroutines."""
        pytest.importorskip("numpy")
        import numpy as np

        keys = [(NS, SET_NAME, f"anp_{i}") for i in range(20)]
        await asyncio.gather(*(async_client.put(k, {"score": i * 5}) for i, k in enumerate(keys)))

        dtype = np.dtype([("score", "i4")])

        async def numpy_read():
            result = await async_client.batch_read(keys, bins=["score"], _dtype=dtype)
            assert len(result) == 20

        await asyncio.gather(*(numpy_read() for _ in range(4)))

        await asyncio.gather(*(async_client.remove(k) for k in keys))


class TestExtendedAsyncConcurrency:
    """Additional async concurrency tests covering mixed operations and edge cases."""

    async def test_gather_mixed_operations(self, async_client):
        """asyncio.gather with put, get, remove, exists on different keys simultaneously."""
        key_put = (NS, SET_NAME, "amix_put")
        key_get = (NS, SET_NAME, "amix_get")
        key_rm = (NS, SET_NAME, "amix_rm")
        key_ex = (NS, SET_NAME, "amix_ex")

        # Pre-populate keys that will be read/removed/checked
        await async_client.put(key_get, {"v": 100})
        await async_client.put(key_rm, {"v": 200})
        await async_client.put(key_ex, {"v": 300})

        async def do_put():
            await async_client.put(key_put, {"v": 42})

        async def do_get():
            _, _, bins = await async_client.get(key_get)
            assert bins["v"] == 100

        async def do_remove():
            await async_client.remove(key_rm)

        async def do_exists():
            result = await async_client.exists(key_ex)
            assert result.meta is not None

        await asyncio.gather(do_put(), do_get(), do_remove(), do_exists())

        # Verify put worked
        _, _, bins = await async_client.get(key_put)
        assert bins["v"] == 42

        # Verify remove worked
        with pytest.raises(aerospike_py.RecordNotFound):
            await async_client.get(key_rm)

        # Cleanup
        await async_client.remove(key_put)
        await async_client.remove(key_get)
        await async_client.remove(key_ex)

    async def test_semaphore_bounded_small(self, async_client):
        """Semaphore(10) controlling 100 concurrent tasks without pool exhaustion."""
        sem = asyncio.Semaphore(10)

        async def bounded_op(i):
            async with sem:
                key = (NS, SET_NAME, f"asem10_{i}")
                await async_client.put(key, {"v": i})
                _, _, bins = await async_client.get(key)
                assert bins["v"] == i
                await async_client.remove(key)

        await asyncio.gather(*(bounded_op(i) for i in range(100)))

    async def test_concurrent_batch_read_multi(self, async_client):
        """8 concurrent async tasks performing batch_read on shared keys."""
        keys = [(NS, SET_NAME, f"abrm_{i}") for i in range(50)]
        await asyncio.gather(*(async_client.put(k, {"v": int(k[2].split("_")[1])}) for k in keys))

        async def batch_reader():
            result = await async_client.batch_read(keys, bins=["v"])
            assert len(result.batch_records) == 50

        await asyncio.gather(*(batch_reader() for _ in range(8)))
        await asyncio.gather(*(async_client.remove(k) for k in keys))

    async def test_concurrent_operate_async(self, async_client):
        """Multiple async tasks call operate() (increment) on the same key."""
        key = (NS, SET_NAME, "aop_incr")
        await async_client.put(key, {"counter": 0})
        num_tasks = 10
        ops_per_task = 10

        ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1}]

        async def do_operate():
            for _ in range(ops_per_task):
                await async_client.operate(key, ops)

        await asyncio.gather(*(do_operate() for _ in range(num_tasks)))

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == num_tasks * ops_per_task
        await async_client.remove(key)

    async def test_rapid_connect_disconnect_concurrent(self):
        """Concurrent rapid connect/close cycles for stability."""
        # Check server availability before spawning concurrent tasks
        probe = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        try:
            await probe.connect()
        except Exception:
            pytest.skip("Aerospike server not available")
        await probe.close()

        async def connect_cycle():
            c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
            await c.connect()
            assert c.is_connected()
            await c.close()
            assert not c.is_connected()

        await asyncio.gather(*(connect_cycle() for _ in range(5)))

    async def test_concurrent_exists_async(self, async_client):
        """Many async tasks call exists() concurrently on shared keys."""
        keys = [(NS, SET_NAME, f"aex_{i}") for i in range(30)]
        await asyncio.gather(*(async_client.put(k, {"v": 1}) for k in keys))

        async def exists_task():
            for k in keys:
                result = await async_client.exists(k)
                assert result.meta is not None

        await asyncio.gather(*(exists_task() for _ in range(5)))
        await asyncio.gather(*(async_client.remove(k) for k in keys))

    async def test_concurrent_select_async(self, async_client):
        """Many async tasks call select() concurrently."""
        keys = [(NS, SET_NAME, f"asel_{i}") for i in range(20)]
        await asyncio.gather(*(async_client.put(k, {"a": 1, "b": 2, "c": 3}) for k in keys))

        async def select_task():
            for k in keys:
                _, _, bins = await async_client.select(k, ["a", "b"])
                assert "a" in bins
                assert "b" in bins

        await asyncio.gather(*(select_task() for _ in range(5)))
        await asyncio.gather(*(async_client.remove(k) for k in keys))

    async def test_concurrent_touch_async(self, async_client):
        """Many async tasks call touch() concurrently."""
        keys = [(NS, SET_NAME, f"atc_{i}") for i in range(20)]
        await asyncio.gather(*(async_client.put(k, {"v": 1}) for k in keys))

        async def touch_task():
            for k in keys:
                await async_client.touch(k)

        await asyncio.gather(*(touch_task() for _ in range(5)))
        await asyncio.gather(*(async_client.remove(k) for k in keys))

    async def test_concurrent_increment_async(self, async_client):
        """Many async tasks increment the same key; final value must match total ops."""
        key = (NS, SET_NAME, "ainc_conc")
        await async_client.put(key, {"counter": 0})
        num_tasks = 10
        increments_per_task = 20

        async def inc_task():
            for _ in range(increments_per_task):
                await async_client.increment(key, "counter", 1)

        await asyncio.gather(*(inc_task() for _ in range(num_tasks)))

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == num_tasks * increments_per_task
        await async_client.remove(key)
