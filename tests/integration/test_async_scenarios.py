"""Async-only scenario tests (operations that have no sync equivalent).

Shared sync/async scenarios live in ``test_scenarios.py`` and are run via
the ``any_client`` parametrized fixture.  This file covers async-specific
behaviour such as ``asyncio.gather`` concurrency, async truncate, and
async UDF invocation.
"""

import asyncio

import pytest

import aerospike_py
from aerospike_py import AsyncClient


class TestAsyncConcurrentOps:
    """Test concurrent async operations."""

    async def test_concurrent_puts(self, async_client, async_cleanup):
        keys = [("test", "async_scen", f"conc_{i}") for i in range(10)]
        async_cleanup.extend(keys)

        tasks = [async_client.put(key, {"idx": i}) for i, key in enumerate(keys)]
        await asyncio.gather(*tasks)

        result = await async_client.batch_read(keys)
        assert len(result.batch_records) == 10
        idxs = sorted([br.record.bins["idx"] for br in result.batch_records if br.record is not None])
        assert idxs == list(range(10))

    async def test_concurrent_reads_writes(self, async_client, async_cleanup):
        key = ("test", "async_scen", "conc_rw")
        async_cleanup.append(key)

        await async_client.put(key, {"counter": 0})

        tasks = [async_client.increment(key, "counter", 1) for _ in range(10)]
        await asyncio.gather(*tasks)

        _, _, bins = await async_client.get(key)
        assert bins["counter"] == 10


class TestAsyncTruncate:
    """Async truncate scenario tests."""

    async def test_truncate_set(self, async_client):
        ns = "test"
        set_name = "async_trunc"
        keys = [(ns, set_name, f"t_{i}") for i in range(3)]
        for key in keys:
            await async_client.put(key, {"v": 1})

        await async_client.truncate(ns, set_name)


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


class TestAsyncErrorHandling:
    """Async-specific error handling (client lifecycle differs from sync)."""

    async def test_double_close(self, async_client):
        await async_client.close()
        await async_client.close()

    async def test_operations_after_close(self, async_client):
        await async_client.close()
        with pytest.raises(aerospike_py.AerospikeError):
            await async_client.get(("test", "demo", "key"))

    async def test_connect_bad_host(self):
        c = AsyncClient({"hosts": [("192.0.2.1", 9999)], "timeout": 1000})
        with pytest.raises(aerospike_py.AerospikeError):
            await c.connect()


class TestAsyncDataTypes:
    """Async-specific data type tests (comprehensive single-record check)."""

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
