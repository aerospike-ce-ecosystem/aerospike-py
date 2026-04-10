"""Integration tests for AsyncClient (requires Aerospike server).

Note: CRUD, batch_read, exists, touch, increment, and operate tests are
covered by ``test_scenarios.py`` via the ``any_client`` fixture (sync+async).
This file only contains async-specific tests (connection management) and
batch_operate scenarios not yet covered by any_client tests.
"""

import aerospike_py


class TestAsyncConnection:
    async def test_is_connected(self, async_client):
        assert async_client.is_connected()

    async def test_close(self, async_client):
        assert async_client.is_connected()
        await async_client.close()
        assert not async_client.is_connected()

    async def test_get_node_names(self, async_client):
        """get_node_names() is sync on AsyncClient since alpha.10 — no await."""
        names = async_client.get_node_names()
        assert isinstance(names, list)
        assert len(names) > 0
        assert all(isinstance(n, str) for n in names)


class TestAsyncBatchWrite:
    """Test async batch_operate used as batch write (OPERATOR_WRITE)."""

    async def test_async_batch_write_new_records(self, async_client, async_cleanup):
        keys = [
            ("test", "demo", "async_bw_1"),
            ("test", "demo", "async_bw_2"),
            ("test", "demo", "async_bw_3"),
        ]
        for k in keys:
            async_cleanup.append(k)

        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "name", "val": "async_test"},
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "score", "val": 200},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0
            assert br.in_doubt is False

        # Verify records were written
        for k in keys:
            _, meta, bins = await async_client.get(k)
            assert meta is not None
            assert bins["name"] == "async_test"
            assert bins["score"] == 200

    async def test_async_batch_write_partial_failure(self, async_client, async_cleanup):
        """OPERATOR_INCR on string bin causes per-record failure."""
        keys = [
            ("test", "demo", "async_bwf_ok"),
            ("test", "demo", "async_bwf_fail"),
        ]
        for k in keys:
            async_cleanup.append(k)

        await async_client.put(keys[0], {"counter": 10})
        await async_client.put(keys[1], {"counter": "not_a_number"})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2

        # First record succeeds
        br0 = results.batch_records[0]
        assert br0.result == 0
        assert br0.record is not None
        assert br0.record.meta is not None

        # Second record fails (type mismatch)
        br1 = results.batch_records[1]
        assert br1.result != 0
        assert br1.record is None

    async def test_async_batch_write_with_read_back(self, async_client, async_cleanup):
        keys = [
            ("test", "demo", "async_bwr_1"),
            ("test", "demo", "async_bwr_2"),
        ]
        for k in keys:
            async_cleanup.append(k)

        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "val", "val": 77},
            {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.in_doubt is False
            assert br.record is not None
            val = br.record.bins["val"]
            if isinstance(val, list):
                assert val[-1] == 77
            else:
                assert val == 77


class TestAsyncBatchWriteGeneric:
    """Test async batch_write() — generic dict-based batch write."""

    async def test_async_batch_write_new_records(self, async_client, async_cleanup):
        records = [
            (("test", "demo", "abw_gen_1"), {"name": "Alice", "age": 30}),
            (("test", "demo", "abw_gen_2"), {"name": "Bob", "age": 25}),
        ]
        for key, _ in records:
            async_cleanup.append(key)

        results = await async_client.batch_write(records)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.in_doubt is False

        # Verify
        _, _, bins = await async_client.get(("test", "demo", "abw_gen_1"))
        assert bins["name"] == "Alice"
        assert bins["age"] == 30

    async def test_async_batch_write_different_bins(self, async_client, async_cleanup):
        records = [
            (("test", "demo", "abw_diff_1"), {"x": 1}),
            (("test", "demo", "abw_diff_2"), {"a": "hello", "b": 42}),
        ]
        for key, _ in records:
            async_cleanup.append(key)

        results = await async_client.batch_write(records)
        for br in results.batch_records:
            assert br.result == 0
            assert br.in_doubt is False

        _, _, bins = await async_client.get(("test", "demo", "abw_diff_2"))
        assert bins == {"a": "hello", "b": 42}

    async def test_async_batch_write_empty(self, async_client):
        results = await async_client.batch_write([])
        assert len(results.batch_records) == 0


class TestAsyncBatchWriteTTL:
    """Test async batch_write() TTL support."""

    async def test_async_batch_write_policy_ttl(self, async_client, async_cleanup):
        """Batch-level TTL via policy is applied to all records."""
        keys = [
            ("test", "demo", "abw_ttl_pol_1"),
            ("test", "demo", "abw_ttl_pol_2"),
        ]
        for k in keys:
            async_cleanup.append(k)

        ttl_seconds = 2592000  # 30 days
        records = [(k, {"val": i}) for i, k in enumerate(keys)]
        results = await async_client.batch_write(records, policy={"ttl": ttl_seconds})
        for br in results.batch_records:
            assert br.result == 0

        for k in keys:
            _, meta, _ = await async_client.get(k)
            assert meta is not None
            assert meta.ttl > 0
            assert meta.ttl <= ttl_seconds

    async def test_async_batch_write_per_record_meta_ttl(self, async_client, async_cleanup):
        """Per-record TTL via (key, bins, meta) tuple."""
        key = ("test", "demo", "abw_ttl_meta")
        async_cleanup.append(key)

        ttl_seconds = 3600
        results = await async_client.batch_write([(key, {"val": 1}, {"ttl": ttl_seconds})])
        assert results.batch_records[0].result == 0

        _, meta, _ = await async_client.get(key)
        assert meta is not None
        assert meta.ttl > 0
        assert meta.ttl <= ttl_seconds

    async def test_async_batch_write_ttl_never_expire(self, async_client, async_cleanup):
        """TTL_NEVER_EXPIRE via policy in async batch_write."""
        key = ("test", "demo", "abw_ttl_never")
        async_cleanup.append(key)

        results = await async_client.batch_write(
            [(key, {"val": 1})],
            policy={"ttl": aerospike_py.TTL_NEVER_EXPIRE},
        )
        assert results.batch_records[0].result == 0

        _, meta, _ = await async_client.get(key)
        assert meta is not None
        assert meta.ttl > 0

    async def test_async_batch_write_per_record_meta_overrides_policy_ttl(self, async_client, async_cleanup):
        """Per-record meta TTL overrides batch-level policy TTL."""
        key_policy = ("test", "demo", "abw_ttl_override_pol")
        key_meta = ("test", "demo", "abw_ttl_override_meta")
        async_cleanup.append(key_policy)
        async_cleanup.append(key_meta)

        policy_ttl = 86400  # 1 day
        meta_ttl = 3600  # 1 hour

        records = [
            (key_policy, {"val": 1}),  # uses batch-level TTL
            (key_meta, {"val": 2}, {"ttl": meta_ttl}),  # overrides with per-record TTL
        ]
        results = await async_client.batch_write(records, policy={"ttl": policy_ttl})
        for br in results.batch_records:
            assert br.result == 0

        _, meta_pol, _ = await async_client.get(key_policy)
        assert meta_pol is not None
        assert meta_pol.ttl > 3600

        _, meta_m, _ = await async_client.get(key_meta)
        assert meta_m is not None
        assert meta_m.ttl <= meta_ttl
        assert meta_m.ttl > 0

    async def test_async_batch_write_ttl_dont_update(self, async_client, async_cleanup):
        """TTL_DONT_UPDATE preserves original TTL while updating bins."""
        key = ("test", "demo", "abw_ttl_dont_upd")
        async_cleanup.append(key)

        await async_client.put(key, {"val": 1}, meta={"ttl": 3600})

        results = await async_client.batch_write([(key, {"val": 2}, {"ttl": aerospike_py.TTL_DONT_UPDATE})])
        assert results.batch_records[0].result == 0

        _, meta, bins = await async_client.get(key)
        assert bins["val"] == 2
        assert meta.ttl > 3000

    async def test_async_batch_write_mixed_ttl_in_batch(self, async_client, async_cleanup):
        """Different TTL values per record in a single batch call."""
        key_a = ("test", "demo", "abw_ttl_mix_a")
        key_b = ("test", "demo", "abw_ttl_mix_b")
        key_c = ("test", "demo", "abw_ttl_mix_c")
        for k in (key_a, key_b, key_c):
            async_cleanup.append(k)

        records = [
            (key_a, {"val": 1}, {"ttl": 3600}),
            (key_b, {"val": 2}, {"ttl": 86400}),
            (key_c, {"val": 3}),
        ]
        results = await async_client.batch_write(records, policy={"ttl": 300})
        for br in results.batch_records:
            assert br.result == 0

        _, meta_a, _ = await async_client.get(key_a)
        _, meta_b, _ = await async_client.get(key_b)
        _, meta_c, _ = await async_client.get(key_c)

        assert meta_a.ttl > 300
        assert meta_a.ttl <= 3600
        assert meta_b.ttl > 3600
        assert meta_b.ttl <= 86400
        assert meta_c.ttl > 0
        assert meta_c.ttl <= 300


class TestAsyncBatchWriteGen:
    """Test async batch_write() generation (CAS) support via per-record meta."""

    async def test_async_batch_write_gen_check_success(self, async_client, async_cleanup):
        """Per-record gen check succeeds when generation matches."""
        key = ("test", "demo", "abw_gen_ok")
        async_cleanup.append(key)
        await async_client.put(key, {"val": 1})
        _, meta, _ = await async_client.get(key)
        current_gen = meta.gen

        results = await async_client.batch_write([(key, {"val": 2}, {"gen": current_gen})])
        assert results.batch_records[0].result == 0
        _, _, bins = await async_client.get(key)
        assert bins["val"] == 2

    async def test_async_batch_write_gen_check_mismatch(self, async_client, async_cleanup):
        """Per-record gen check fails when generation does not match."""
        key = ("test", "demo", "abw_gen_mismatch")
        async_cleanup.append(key)
        await async_client.put(key, {"val": 1})

        results = await async_client.batch_write([(key, {"val": 2}, {"gen": 999})])
        assert results.batch_records[0].result != 0

    async def test_async_batch_write_gen_and_ttl_combined(self, async_client, async_cleanup):
        """Gen and TTL can be used together in WriteMeta."""
        key = ("test", "demo", "abw_gen_ttl")
        async_cleanup.append(key)
        await async_client.put(key, {"val": 1})
        _, meta, _ = await async_client.get(key)
        current_gen = meta.gen

        results = await async_client.batch_write([(key, {"val": 2}, {"gen": current_gen, "ttl": 3600})])
        assert results.batch_records[0].result == 0
        _, meta2, bins = await async_client.get(key)
        assert bins["val"] == 2
        assert meta2.ttl > 0
        assert meta2.ttl <= 3600
