"""End-to-end async scenario tests."""

import asyncio

import pytest

import aerospike_py
from aerospike_py import AsyncClient


class TestAsyncCRUDWorkflow:
    """Async multi-step CRUD scenarios."""

    async def test_full_lifecycle(self, async_client, async_cleanup):
        key = ("test", "async_scen", "lifecycle")
        async_cleanup.append(key)

        await async_client.put(key, {"name": "Alice", "age": 25})
        _, meta1, bins = await async_client.get(key)
        assert bins["name"] == "Alice"
        assert bins["age"] == 25
        gen1 = meta1.gen

        await async_client.put(key, {"age": 26})
        _, meta2, bins = await async_client.get(key)
        assert bins["name"] == "Alice"
        assert bins["age"] == 26
        assert meta2.gen == gen1 + 1

        await async_client.remove(key)
        _, meta = await async_client.exists(key)
        assert meta is None

    async def test_increment_sequence(self, async_client, async_cleanup):
        key = ("test", "async_scen", "incr_seq")
        async_cleanup.append(key)

        await async_client.put(key, {"counter": 0})
        for _ in range(5):
            await async_client.increment(key, "counter", 3)

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == 15

    async def test_operate_atomic(self, async_client, async_cleanup):
        key = ("test", "async_scen", "operate_atomic")
        async_cleanup.append(key)

        await async_client.put(key, {"a": 10, "b": "hello"})
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "a", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "b", "val": None},
        ]
        _, _, bins = await async_client.operate(key, ops)
        assert bins["a"] == 15
        assert bins["b"] == "hello"


class TestAsyncBatchWorkflow:
    """Async batch operation scenarios."""

    async def test_bulk_write_batch_read(self, async_client, async_cleanup):
        keys = [("test", "async_scen", f"batch_{i}") for i in range(5)]
        async_cleanup.extend(keys)

        for i, key in enumerate(keys):
            await async_client.put(key, {"idx": i})

        result = await async_client.batch_read(keys)
        assert len(result.batch_records) == 5
        for i, br in enumerate(result.batch_records):
            assert br.result == 0
            _, meta, bins = br.record
            assert meta is not None
            assert bins["idx"] == i

    async def test_batch_remove_verify(self, async_client):
        keys = [("test", "async_scen", f"brem_{i}") for i in range(3)]
        for key in keys:
            await async_client.put(key, {"val": 1})

        await async_client.batch_remove(keys)

        result = await async_client.batch_read(keys, bins=[])
        for br in result.batch_records:
            assert br.result == 2  # KEY_NOT_FOUND


class TestAsyncDataTypes:
    """Async data type edge case scenarios."""

    async def test_various_types(self, async_client, async_cleanup):
        key = ("test", "async_scen", "types")
        async_cleanup.append(key)

        data = {
            "int": 42,
            "float": 3.14,
            "str": "hello 한글",
            "bytes": b"\x00\x01\x02",
            "list": [1, "two", 3.0],
            "map": {"nested": {"deep": True}},
            "bool": False,
        }
        await async_client.put(key, data)
        _, _, bins = await async_client.get(key)

        assert bins["int"] == 42
        assert abs(bins["float"] - 3.14) < 0.001
        assert bins["str"] == "hello 한글"
        assert bins["bytes"] == b"\x00\x01\x02"
        assert bins["list"] == [1, "two", 3.0]
        assert bins["map"]["nested"]["deep"] is True
        assert bins["bool"] is False

    async def test_large_record(self, async_client, async_cleanup):
        key = ("test", "async_scen", "large")
        async_cleanup.append(key)

        large_str = "x" * 50_000
        large_list = list(range(1000))
        await async_client.put(key, {"str": large_str, "list": large_list})
        _, _, bins = await async_client.get(key)
        assert len(bins["str"]) == 50_000
        assert len(bins["list"]) == 1000


class TestAsyncErrorHandling:
    """Async error handling scenarios."""

    async def test_get_nonexistent(self, async_client):
        with pytest.raises(aerospike_py.RecordNotFound):
            await async_client.get(("test", "async_scen", "nonexistent_xyz"))

    async def test_double_close(self, async_client):
        await async_client.close()
        await async_client.close()  # Should not raise

    async def test_operations_after_close(self, async_client):
        await async_client.close()
        with pytest.raises(aerospike_py.AerospikeError):
            await async_client.get(("test", "demo", "key"))

    async def test_connect_bad_host(self):
        c = AsyncClient({"hosts": [("192.0.2.1", 9999)], "timeout": 1000})
        with pytest.raises(aerospike_py.AerospikeError):
            await c.connect()


class TestAsyncScanWorkflow:
    """Async scan scenario tests."""

    async def test_scan_after_writes(self, async_client, async_cleanup):
        ns = "test"
        set_name = "async_scan_scen"
        keys = [(ns, set_name, f"s_{i}") for i in range(5)]
        async_cleanup.extend(keys)

        for i, key in enumerate(keys):
            await async_client.put(key, {"idx": i, "val": i * 10})

        results = await async_client.scan(ns, set_name)
        assert len(results) >= 5

        idxs = [bins["idx"] for _, _, bins in results]
        for i in range(5):
            assert i in idxs


class TestAsyncTruncate:
    """Async truncate scenario tests."""

    async def test_truncate_set(self, async_client):
        ns = "test"
        set_name = "async_trunc"
        keys = [(ns, set_name, f"t_{i}") for i in range(3)]
        for key in keys:
            await async_client.put(key, {"v": 1})

        await async_client.truncate(ns, set_name)
        # Truncate is async on server side, so just verify no error


class TestAsyncUDF:
    """Async UDF scenario tests."""

    async def test_apply_udf(self, async_client, async_cleanup):
        key = ("test", "async_scen", "udf_test")
        async_cleanup.append(key)

        try:
            await async_client.udf_put("tests/test_udf.lua")

            await async_client.put(key, {"val": 42})

            result = await async_client.apply(key, "test_udf", "echo", [100])
            assert result == 100

            result = await async_client.apply(key, "test_udf", "get_bin", ["val"])
            assert result == 42
        except aerospike_py.AerospikeError as e:
            if "udf" in str(e).lower():
                pytest.skip("UDF not available")
            raise
        finally:
            try:
                await async_client.udf_remove("test_udf")
            except Exception:
                pass


class TestAsyncConcurrentOps:
    """Test concurrent async operations."""

    async def test_concurrent_puts(self, async_client, async_cleanup):
        keys = [("test", "async_scen", f"conc_{i}") for i in range(10)]
        async_cleanup.extend(keys)

        tasks = [async_client.put(key, {"idx": i}) for i, key in enumerate(keys)]
        await asyncio.gather(*tasks)

        result = await async_client.batch_read(keys)
        assert len(result.batch_records) == 10
        idxs = sorted([br.record[2]["idx"] for br in result.batch_records if br.record is not None])
        assert idxs == list(range(10))

    async def test_concurrent_reads_writes(self, async_client, async_cleanup):
        key = ("test", "async_scen", "conc_rw")
        async_cleanup.append(key)

        await async_client.put(key, {"counter": 0})

        tasks = [async_client.increment(key, "counter", 1) for _ in range(10)]
        await asyncio.gather(*tasks)

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == 10
