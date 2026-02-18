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


class TestAsyncTTLScenarios:
    """Async TTL (time-to-live) scenarios."""

    async def test_ttl_set_and_verify(self, async_client, async_cleanup):
        """Set TTL and verify it's within expected range."""
        key = ("test", "async_scen", "ttl_1")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1}, meta={"ttl": 600})
        _, meta, _ = await async_client.get(key)
        assert 0 < meta.ttl <= 600

    async def test_ttl_touch_extends(self, async_client, async_cleanup):
        """Touch should extend TTL."""
        key = ("test", "async_scen", "ttl_touch")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1}, meta={"ttl": 100})
        _, meta1, _ = await async_client.get(key)
        original_ttl = meta1.ttl

        await async_client.touch(key, 1000)
        _, meta2, _ = await async_client.get(key)
        assert meta2.ttl > original_ttl

    async def test_ttl_never_expire(self, async_client, async_cleanup):
        """Set TTL to never expire."""
        key = ("test", "async_scen", "ttl_never")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1}, meta={"ttl": aerospike_py.TTL_NEVER_EXPIRE})
        _, meta, _ = await async_client.get(key)
        assert meta.ttl > 0


class TestAsyncGenerationPolicy:
    """Async generation (optimistic locking) scenarios."""

    async def test_generation_increments(self, async_client, async_cleanup):
        """Each write should increment generation."""
        key = ("test", "async_scen", "gen_inc")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1})
        _, meta1, _ = await async_client.get(key)
        assert meta1.gen == 1

        await async_client.put(key, {"val": 2})
        _, meta2, _ = await async_client.get(key)
        assert meta2.gen == 2

        await async_client.put(key, {"val": 3})
        _, meta3, _ = await async_client.get(key)
        assert meta3.gen == 3

    async def test_generation_eq_policy_success(self, async_client, async_cleanup):
        """Write with gen=current should succeed."""
        key = ("test", "async_scen", "gen_eq_ok")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1})
        _, meta, _ = await async_client.get(key)

        await async_client.put(
            key,
            {"val": 2},
            meta={"gen": meta.gen},
            policy={"gen": aerospike_py.POLICY_GEN_EQ},
        )
        _, meta2, bins = await async_client.get(key)
        assert bins["val"] == 2

    async def test_generation_eq_policy_failure(self, async_client, async_cleanup):
        """Write with stale generation should fail."""
        key = ("test", "async_scen", "gen_eq_fail")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordGenerationError):
            await async_client.put(
                key,
                {"val": 2},
                meta={"gen": 999},
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )

        _, _, bins = await async_client.get(key)
        assert bins["val"] == 1


class TestAsyncExistsPolicy:
    """Async record-exists policy scenarios."""

    async def test_create_only_success(self, async_client, async_cleanup):
        """CREATE_ONLY should succeed when record doesn't exist."""
        key = ("test", "async_scen", "create_only_ok")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == 1

    async def test_create_only_failure(self, async_client, async_cleanup):
        """CREATE_ONLY should fail when record already exists."""
        key = ("test", "async_scen", "create_only_fail")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordExistsError):
            await async_client.put(
                key,
                {"val": 2},
                policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )

        _, _, bins = await async_client.get(key)
        assert bins["val"] == 1

    async def test_update_only_success(self, async_client, async_cleanup):
        """UPDATE_ONLY should succeed when record exists."""
        key = ("test", "async_scen", "update_only_ok")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1})
        await async_client.put(key, {"val": 2}, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == 2

    async def test_update_only_failure(self, async_client):
        """UPDATE_ONLY should fail when record doesn't exist."""
        key = ("test", "async_scen", "update_only_fail")

        with pytest.raises(aerospike_py.AerospikeError):
            await async_client.put(key, {"val": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE})


class TestAsyncSelectVariations:
    """Async select operation scenarios."""

    async def test_select_nonexistent_bin(self, async_client, async_cleanup):
        """Selecting a bin that doesn't exist should return without it."""
        key = ("test", "async_scen", "select_missing")
        async_cleanup.append(key)

        await async_client.put(key, {"a": 1, "b": 2})
        _, _, bins = await async_client.select(key, ["a", "nonexistent"])
        assert bins["a"] == 1
        assert "nonexistent" not in bins

    async def test_select_all_bins(self, async_client, async_cleanup):
        """Selecting all existing bins returns all."""
        key = ("test", "async_scen", "select_all")
        async_cleanup.append(key)

        await async_client.put(key, {"x": 10, "y": 20, "z": 30})
        _, _, bins = await async_client.select(key, ["x", "y", "z"])
        assert bins == {"x": 10, "y": 20, "z": 30}

    async def test_select_single_bin(self, async_client, async_cleanup):
        """Selecting a single bin from many."""
        key = ("test", "async_scen", "select_single")
        async_cleanup.append(key)

        await async_client.put(key, {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
        _, _, bins = await async_client.select(key, ["c"])
        assert bins == {"c": 3}


class TestAsyncOperateOrdered:
    """Async operate_ordered scenarios."""

    async def test_ordered_multiple_reads(self, async_client, async_cleanup):
        key = ("test", "async_scen", "ordered_reads")
        async_cleanup.append(key)

        await async_client.put(key, {"a": 1, "b": 2, "c": 3})
        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "c", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "b", "val": None},
        ]
        _, meta, ordered = await async_client.operate_ordered(key, ops)
        assert isinstance(ordered, list)
        assert meta.gen >= 1
        for item in ordered:
            assert isinstance(item, tuple)
            assert len(item) == 2

    async def test_ordered_write_then_read(self, async_client, async_cleanup):
        key = ("test", "async_scen", "ordered_wr")
        async_cleanup.append(key)

        await async_client.put(key, {"counter": 0})
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 10},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        _, _, ordered = await async_client.operate_ordered(key, ops)
        found = False
        for name, val in ordered:
            if name == "counter":
                assert val == 10
                found = True
        assert found


class TestAsyncDataTypeEdgeCases:
    """Async edge cases for various data types."""

    async def test_empty_string(self, async_client, async_cleanup):
        key = ("test", "async_scen", "empty_str")
        async_cleanup.append(key)
        await async_client.put(key, {"val": ""})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == ""

    async def test_large_string(self, async_client, async_cleanup):
        key = ("test", "async_scen", "large_str")
        async_cleanup.append(key)
        large = "x" * 100_000
        await async_client.put(key, {"val": large})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == large
        assert len(bins["val"]) == 100_000

    async def test_unicode_string(self, async_client, async_cleanup):
        key = ("test", "async_scen", "unicode_str")
        async_cleanup.append(key)
        await async_client.put(key, {"val": "한글 테스트 🎉 日本語 العربية"})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == "한글 테스트 🎉 日本語 العربية"

    async def test_bytes_key(self, async_client, async_cleanup):
        """Test bytes primary key."""
        key = ("test", "async_scen", b"\x01\x02\x03\x04")
        async_cleanup.append(key)
        await async_client.put(key, {"val": "bytes_key"})
        _, _, bins = await async_client.get(key)
        assert bins["val"] == "bytes_key"


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
