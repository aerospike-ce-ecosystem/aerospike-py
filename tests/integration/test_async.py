"""Integration tests for AsyncClient (requires Aerospike server)."""

import aerospike_py


class TestAsyncConnection:
    async def test_is_connected(self, async_client):
        assert async_client.is_connected()

    async def test_close(self, async_client):
        assert async_client.is_connected()
        await async_client.close()
        assert not async_client.is_connected()


class TestAsyncCRUD:
    async def test_put_and_get(self, async_client):
        key = ("test", "demo", "async_key1")
        await async_client.put(key, {"name": "async", "val": 42})
        _, meta, bins = await async_client.get(key)
        assert bins["name"] == "async"
        assert bins["val"] == 42
        assert meta["gen"] >= 1
        await async_client.remove(key)

    async def test_exists(self, async_client):
        key = ("test", "demo", "async_exists")
        await async_client.put(key, {"a": 1})
        k, meta = await async_client.exists(key)
        assert meta is not None

        await async_client.remove(key)
        k, meta = await async_client.exists(key)
        assert meta is None

    async def test_touch_and_increment(self, async_client):
        key = ("test", "demo", "async_touch")
        await async_client.put(key, {"counter": 10})
        await async_client.touch(key)
        await async_client.increment(key, "counter", 5)
        _, _, bins = await async_client.get(key)
        assert bins["counter"] == 15
        await async_client.remove(key)

    async def test_operate(self, async_client):
        key = ("test", "demo", "async_operate")
        await async_client.put(key, {"a": 1, "b": "hello"})
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "a", "val": 10},
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": None},
        ]
        _, _, bins = await async_client.operate(key, ops)
        val = bins["a"]
        if isinstance(val, list):
            assert val[-1] == 11
        else:
            assert val == 11
        await async_client.remove(key)


class TestAsyncBatch:
    async def test_get_many(self, async_client):
        keys = [
            ("test", "demo", "async_batch_1"),
            ("test", "demo", "async_batch_2"),
        ]
        await async_client.put(keys[0], {"v": 1})
        await async_client.put(keys[1], {"v": 2})
        results = await async_client.get_many(keys)
        assert len(results) == 2
        for _, meta, bins in results:
            assert meta is not None
            assert "v" in bins
        await async_client.batch_remove(keys)

    async def test_exists_many(self, async_client):
        keys = [
            ("test", "demo", "async_em_1"),
            ("test", "demo", "async_em_missing"),
        ]
        await async_client.put(keys[0], {"v": 1})
        results = await async_client.exists_many(keys)
        assert len(results) == 2
        _, meta0 = results[0]
        _, meta1 = results[1]
        assert meta0 is not None
        assert meta1 is None
        await async_client.remove(keys[0])


class TestAsyncScan:
    async def test_scan(self, async_client):
        key = ("test", "demo", "async_scan_1")
        await async_client.put(key, {"s": "data"})
        results = await async_client.scan("test", "demo")
        assert len(results) >= 1
        await async_client.remove(key)
