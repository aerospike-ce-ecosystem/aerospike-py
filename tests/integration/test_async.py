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
        assert meta.gen >= 1
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
    async def test_batch_read(self, async_client):
        keys = [
            ("test", "demo", "async_batch_1"),
            ("test", "demo", "async_batch_2"),
        ]
        await async_client.put(keys[0], {"v": 1})
        await async_client.put(keys[1], {"v": 2})
        result = await async_client.batch_read(keys)
        assert len(result.batch_records) == 2
        for br in result.batch_records:
            assert br.result == 0
            assert br.record is not None
            _, meta, bins = br.record
            assert meta is not None
            assert "v" in bins
        await async_client.batch_remove(keys)

    async def test_batch_read_exists(self, async_client):
        keys = [
            ("test", "demo", "async_em_1"),
            ("test", "demo", "async_em_missing"),
        ]
        await async_client.put(keys[0], {"v": 1})
        result = await async_client.batch_read(keys, bins=[])
        assert len(result.batch_records) == 2
        assert result.batch_records[0].result == 0
        assert result.batch_records[1].result == 2  # KEY_NOT_FOUND
        await async_client.remove(keys[0])


class TestAsyncBatchWrite:
    """Test async batch_operate used as batch write (OPERATOR_WRITE)."""

    async def test_async_batch_write_new_records(self, async_client):
        keys = [
            ("test", "demo", "async_bw_1"),
            ("test", "demo", "async_bw_2"),
            ("test", "demo", "async_bw_3"),
        ]
        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "name", "val": "async_test"},
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "score", "val": 200},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results) == 3

        # Verify records were written
        for k in keys:
            _, meta, bins = await async_client.get(k)
            assert meta is not None
            assert bins["name"] == "async_test"
            assert bins["score"] == 200
        await async_client.batch_remove(keys)

    async def test_async_batch_write_partial_failure(self, async_client):
        """OPERATOR_INCR on string bin causes per-record failure."""
        keys = [
            ("test", "demo", "async_bwf_ok"),
            ("test", "demo", "async_bwf_fail"),
        ]
        await async_client.put(keys[0], {"counter": 10})
        await async_client.put(keys[1], {"counter": "not_a_number"})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results) == 2

        # First record succeeds
        _, meta0, bins0 = results[0]
        assert meta0 is not None

        # Second record fails (type mismatch) -> None meta/bins
        _, meta1, bins1 = results[1]
        assert meta1 is None
        assert bins1 is None

        await async_client.batch_remove(keys)

    async def test_async_batch_write_with_read_back(self, async_client):
        keys = [
            ("test", "demo", "async_bwr_1"),
            ("test", "demo", "async_bwr_2"),
        ]
        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "val", "val": 77},
            {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results) == 2
        for rec in results:
            _, meta, bins = rec
            assert meta is not None
            val = bins["val"]
            if isinstance(val, list):
                assert val[-1] == 77
            else:
                assert val == 77
        await async_client.batch_remove(keys)


class TestAsyncScan:
    async def test_scan(self, async_client):
        key = ("test", "demo", "async_scan_1")
        await async_client.put(key, {"s": "data"})
        results = await async_client.scan("test", "demo")
        assert len(results) >= 1
        await async_client.remove(key)
