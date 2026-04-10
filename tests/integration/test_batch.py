"""Integration tests for batch operations (requires Aerospike server)."""

import aerospike_py


class TestBatchRead:
    def test_batch_read_all_bins(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_get_1"),
            ("test", "demo", "batch_get_2"),
            ("test", "demo", "batch_get_3"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"a": 1})
        client.put(keys[1], {"a": 2})
        client.put(keys[2], {"a": 3})

        result = client.batch_read(keys)
        assert isinstance(result, dict)
        assert len(result) == 3
        assert result["batch_get_1"]["a"] == 1
        assert result["batch_get_2"]["a"] == 2
        assert result["batch_get_3"]["a"] == 3

    def test_batch_read_specific_bins(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_select_1"),
            ("test", "demo", "batch_select_2"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"a": 1, "b": 2, "c": 3})
        client.put(keys[1], {"a": 10, "b": 20, "c": 30})

        result = client.batch_read(keys, bins=["a", "c"])
        assert len(result) == 2
        for user_key, bins in result.items():
            assert "a" in bins
            assert "c" in bins
            assert "b" not in bins

    def test_batch_read_exists(self, client, cleanup):
        """bins=[] performs existence check; only found records in dict."""
        keys = [
            ("test", "demo", "batch_exists_1"),
            ("test", "demo", "batch_exists_2"),
            ("test", "demo", "batch_exists_missing"),
        ]
        cleanup.append(keys[0])
        cleanup.append(keys[1])

        client.put(keys[0], {"val": 1})
        client.put(keys[1], {"val": 2})

        result = client.batch_read(keys, bins=[])
        # Only found records appear in dict (missing excluded)
        assert "batch_exists_1" in result
        assert "batch_exists_2" in result
        assert "batch_exists_missing" not in result

    def test_batch_read_with_missing(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_get_exists"),
            ("test", "demo", "batch_get_missing"),
        ]
        cleanup.append(keys[0])

        client.put(keys[0], {"val": 1})

        result = client.batch_read(keys)
        assert len(result) == 1
        assert result["batch_get_exists"]["val"] == 1
        assert "batch_get_missing" not in result


class TestBatchOperate:
    def test_batch_operate(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_op_1"),
            ("test", "demo", "batch_op_2"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"counter": 10})
        client.put(keys[1], {"counter": 20})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        br0 = results.batch_records[0]
        br1 = results.batch_records[1]
        assert br0.result == 0
        assert br1.result == 0
        # Batch operate returns multi-op results as list per bin
        counter0 = br0.record.bins["counter"]
        counter1 = br1.record.bins["counter"]
        if isinstance(counter0, list):
            assert counter0[-1] == 15
            assert counter1[-1] == 25
        else:
            assert counter0 == 15
            assert counter1 == 25


class TestBatchWrite:
    """Test batch_operate used as batch write (OPERATOR_WRITE)."""

    def test_batch_write_new_records(self, client, cleanup):
        """batch_operate with OPERATOR_WRITE creates new records."""
        keys = [
            ("test", "demo", "batch_write_1"),
            ("test", "demo", "batch_write_2"),
            ("test", "demo", "batch_write_3"),
        ]
        for k in keys:
            cleanup.append(k)

        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "name", "val": "test"},
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "score", "val": 100},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0

        # Verify records were written
        for k in keys:
            _, meta, bins = client.get(k)
            assert meta is not None
            assert bins["name"] == "test"
            assert bins["score"] == 100

    def test_batch_write_overwrite_existing(self, client, cleanup):
        """batch_operate with OPERATOR_WRITE overwrites existing records."""
        keys = [
            ("test", "demo", "batch_write_ow_1"),
            ("test", "demo", "batch_write_ow_2"),
        ]
        for k in keys:
            cleanup.append(k)

        # Write initial data
        client.put(keys[0], {"name": "old1", "score": 1})
        client.put(keys[1], {"name": "old2", "score": 2})

        # Overwrite with batch_operate
        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "name", "val": "new"},
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "score", "val": 999},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0

        # Verify overwritten
        for k in keys:
            _, meta, bins = client.get(k)
            assert bins["name"] == "new"
            assert bins["score"] == 999
            assert meta.gen == 2  # generation incremented

    def test_batch_write_partial_failure_mixed_types(self, client, cleanup):
        """batch_operate returns per-record results when some ops fail.

        OPERATOR_INCR on a string bin causes per-record failure while
        other records succeed.
        """
        keys = [
            ("test", "demo", "batch_wf_ok"),
            ("test", "demo", "batch_wf_fail"),
        ]
        for k in keys:
            cleanup.append(k)

        # Setup: first record has int bin, second has string bin
        client.put(keys[0], {"counter": 10})
        client.put(keys[1], {"counter": "not_a_number"})

        # INCR should succeed on int bin but fail on string bin
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2

        # First record should succeed
        br0 = results.batch_records[0]
        assert br0.result == 0
        assert br0.record is not None
        assert br0.record.meta is not None

        # Second record should fail (type mismatch)
        br1 = results.batch_records[1]
        assert br1.result != 0
        assert br1.record is None

    def test_batch_write_with_read_back(self, client, cleanup):
        """batch_operate with WRITE + READ returns written values."""
        keys = [
            ("test", "demo", "batch_wr_1"),
            ("test", "demo", "batch_wr_2"),
        ]
        for k in keys:
            cleanup.append(k)

        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "val", "val": 42},
            {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.record is not None
            val = br.record.bins["val"]
            # batch_operate may return list (multi-op) or scalar
            if isinstance(val, list):
                assert val[-1] == 42
            else:
                assert val == 42

    def test_batch_write_large_batch(self, client, cleanup):
        """batch_operate handles large batches correctly."""
        n = 200
        keys = [("test", "demo", f"batch_wl_{i}") for i in range(n)]
        for k in keys:
            cleanup.append(k)

        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "idx", "val": 0},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == n
        for br in results.batch_records:
            assert br.result == 0

        # Verify all written
        read_result = client.batch_read(keys)
        assert len(read_result) == n


class TestBatchWriteGeneric:
    """Test batch_write() — generic dict-based batch write."""

    def test_batch_write_new_records(self, client, cleanup):
        """Write 3 new records and verify with get()."""
        records = [
            (("test", "demo", "bw_gen_1"), {"name": "Alice", "age": 30}),
            (("test", "demo", "bw_gen_2"), {"name": "Bob", "age": 25}),
            (("test", "demo", "bw_gen_3"), {"name": "Charlie", "age": 35}),
        ]
        for key, _ in records:
            cleanup.append(key)

        results = client.batch_write(records)
        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0
            assert br.in_doubt is False

        # Verify each record
        _, _, bins = client.get(("test", "demo", "bw_gen_1"))
        assert bins["name"] == "Alice"
        assert bins["age"] == 30
        _, _, bins = client.get(("test", "demo", "bw_gen_3"))
        assert bins["name"] == "Charlie"

    def test_batch_write_overwrite_existing(self, client, cleanup):
        """Overwrite existing records and verify generation increments."""
        key = ("test", "demo", "bw_gen_ow")
        cleanup.append(key)

        client.put(key, {"name": "old", "score": 1})
        _, meta_before, _ = client.get(key)

        results = client.batch_write([(key, {"name": "new", "score": 999})])
        assert results.batch_records[0].result == 0

        _, meta_after, bins = client.get(key)
        assert bins["name"] == "new"
        assert bins["score"] == 999
        assert meta_after.gen > meta_before.gen

    def test_batch_write_different_bins_per_key(self, client, cleanup):
        """Each record has different bin names."""
        records = [
            (("test", "demo", "bw_diff_1"), {"x": 1, "y": 2}),
            (("test", "demo", "bw_diff_2"), {"a": "hello", "b": "world", "c": 42}),
        ]
        for key, _ in records:
            cleanup.append(key)

        results = client.batch_write(records)
        for br in results.batch_records:
            assert br.result == 0

        _, _, bins1 = client.get(("test", "demo", "bw_diff_1"))
        assert bins1 == {"x": 1, "y": 2}

        _, _, bins2 = client.get(("test", "demo", "bw_diff_2"))
        assert bins2 == {"a": "hello", "b": "world", "c": 42}

    def test_batch_write_empty_records(self, client):
        """Empty records list returns empty BatchRecords."""
        results = client.batch_write([])
        assert len(results.batch_records) == 0

    def test_batch_write_large_batch(self, client, cleanup):
        """Write 200 records in one batch."""
        n = 200
        records = [(("test", "demo", f"bw_large_{i}"), {"idx": i, "val": f"v{i}"}) for i in range(n)]
        for key, _ in records:
            cleanup.append(key)

        results = client.batch_write(records)
        assert len(results.batch_records) == n
        for br in results.batch_records:
            assert br.result == 0

    def test_batch_write_mixed_types(self, client, cleanup):
        """Write records with different value types."""
        key = ("test", "demo", "bw_mixed")
        cleanup.append(key)

        bins = {
            "str_bin": "hello",
            "int_bin": 42,
            "float_bin": 3.14,
            "list_bin": [1, 2, 3],
            "map_bin": {"nested": "value"},
        }
        results = client.batch_write([(key, bins)])
        assert results.batch_records[0].result == 0

        _, _, read_bins = client.get(key)
        assert read_bins["str_bin"] == "hello"
        assert read_bins["int_bin"] == 42
        assert read_bins["list_bin"] == [1, 2, 3]
        assert read_bins["map_bin"] == {"nested": "value"}

    def test_batch_write_with_policy(self, client, cleanup):
        """Pass a batch policy dict."""
        key = ("test", "demo", "bw_policy")
        cleanup.append(key)

        results = client.batch_write(
            [(key, {"val": 1})],
            policy={"total_timeout": 5000},
        )
        assert results.batch_records[0].result == 0

    def test_batch_write_with_retry(self, client, cleanup):
        """retry parameter is accepted and write succeeds."""
        key = ("test", "demo", "bw_retry")
        cleanup.append(key)

        results = client.batch_write([(key, {"val": 1})], retry=2)
        assert results.batch_records[0].result == 0

        _, _, bins = client.get(key)
        assert bins["val"] == 1


class TestBatchWriteTTL:
    """Test batch_write() TTL support via policy and per-record meta."""

    def test_batch_write_policy_ttl(self, client, cleanup):
        """Batch-level TTL via policy={"ttl": N} is applied to all records."""
        keys = [
            ("test", "demo", "bw_ttl_pol_1"),
            ("test", "demo", "bw_ttl_pol_2"),
        ]
        for k in keys:
            cleanup.append(k)

        ttl_seconds = 2592000  # 30 days
        records = [(k, {"val": i}) for i, k in enumerate(keys)]
        results = client.batch_write(records, policy={"ttl": ttl_seconds})
        for br in results.batch_records:
            assert br.result == 0

        # Verify TTL is set (not namespace default)
        for k in keys:
            _, meta, _ = client.get(k)
            assert meta is not None
            # TTL should be close to what we set (server may subtract a second)
            assert meta.ttl > 0
            assert meta.ttl <= ttl_seconds

    def test_batch_write_per_record_meta_ttl(self, client, cleanup):
        """Per-record TTL via (key, bins, {"ttl": N}) meta tuple."""
        key = ("test", "demo", "bw_ttl_meta")
        cleanup.append(key)

        ttl_seconds = 3600  # 1 hour
        results = client.batch_write([(key, {"val": 1}, {"ttl": ttl_seconds})])
        assert results.batch_records[0].result == 0

        _, meta, _ = client.get(key)
        assert meta is not None
        assert meta.ttl > 0
        assert meta.ttl <= ttl_seconds

    def test_batch_write_per_record_meta_overrides_policy_ttl(self, client, cleanup):
        """Per-record meta TTL overrides batch-level policy TTL."""
        key_policy = ("test", "demo", "bw_ttl_override_pol")
        key_meta = ("test", "demo", "bw_ttl_override_meta")
        cleanup.append(key_policy)
        cleanup.append(key_meta)

        policy_ttl = 86400  # 1 day
        meta_ttl = 3600  # 1 hour

        records = [
            (key_policy, {"val": 1}),  # uses batch-level TTL
            (key_meta, {"val": 2}, {"ttl": meta_ttl}),  # overrides with per-record TTL
        ]
        results = client.batch_write(records, policy={"ttl": policy_ttl})
        for br in results.batch_records:
            assert br.result == 0

        # Record without meta should use batch-level TTL (~1 day)
        _, meta_pol, _ = client.get(key_policy)
        assert meta_pol is not None
        assert meta_pol.ttl > 3600  # should be ~86400, definitely > 1 hour

        # Record with meta should use per-record TTL (~1 hour)
        _, meta_m, _ = client.get(key_meta)
        assert meta_m is not None
        assert meta_m.ttl <= meta_ttl
        assert meta_m.ttl > 0

    def test_batch_write_ttl_never_expire(self, client, cleanup):
        """Batch-level TTL_NEVER_EXPIRE via policy."""
        keys = [
            ("test", "demo", "bw_ttl_never_1"),
            ("test", "demo", "bw_ttl_never_2"),
        ]
        for k in keys:
            cleanup.append(k)

        records = [(k, {"val": i}) for i, k in enumerate(keys)]
        results = client.batch_write(records, policy={"ttl": aerospike_py.TTL_NEVER_EXPIRE})
        for br in results.batch_records:
            assert br.result == 0

        for k in keys:
            _, meta, _ = client.get(k)
            assert meta is not None
            assert meta.ttl > 0  # never expire returns a very large TTL

    def test_batch_write_per_record_meta_never_expire(self, client, cleanup):
        """Per-record meta TTL_NEVER_EXPIRE."""
        key = ("test", "demo", "bw_ttl_meta_never")
        cleanup.append(key)

        results = client.batch_write([(key, {"val": 1}, {"ttl": aerospike_py.TTL_NEVER_EXPIRE})])
        assert results.batch_records[0].result == 0

        _, meta, _ = client.get(key)
        assert meta is not None
        assert meta.ttl > 0

    def test_batch_write_ttl_dont_update(self, client, cleanup):
        """TTL_DONT_UPDATE preserves original TTL while updating bins."""
        key = ("test", "demo", "bw_ttl_dont_upd")
        cleanup.append(key)

        # Step 1: write with explicit TTL
        client.put(key, {"val": 1}, meta={"ttl": 3600})

        # Step 2: update bins via batch_write with DONT_UPDATE
        results = client.batch_write([(key, {"val": 2}, {"ttl": aerospike_py.TTL_DONT_UPDATE})])
        assert results.batch_records[0].result == 0

        _, meta, bins = client.get(key)
        assert bins["val"] == 2  # bins updated
        assert meta.ttl > 3000  # TTL preserved (~3600, minus execution time)

    def test_batch_write_mixed_ttl_in_batch(self, client, cleanup):
        """Different TTL values per record in a single batch call."""
        key_a = ("test", "demo", "bw_ttl_mix_a")
        key_b = ("test", "demo", "bw_ttl_mix_b")
        key_c = ("test", "demo", "bw_ttl_mix_c")
        for k in (key_a, key_b, key_c):
            cleanup.append(k)

        records = [
            (key_a, {"val": 1}, {"ttl": 3600}),  # 1 hour
            (key_b, {"val": 2}, {"ttl": 86400}),  # 1 day
            (key_c, {"val": 3}),  # uses batch policy TTL
        ]
        results = client.batch_write(records, policy={"ttl": 300})
        for br in results.batch_records:
            assert br.result == 0

        _, meta_a, _ = client.get(key_a)
        _, meta_b, _ = client.get(key_b)
        _, meta_c, _ = client.get(key_c)

        # key_a: ~3600
        assert meta_a.ttl > 300
        assert meta_a.ttl <= 3600
        # key_b: ~86400
        assert meta_b.ttl > 3600
        assert meta_b.ttl <= 86400
        # key_c: ~300 (batch policy default)
        assert meta_c.ttl > 0
        assert meta_c.ttl <= 300


class TestBatchWriteGen:
    """Test batch_write() generation (CAS) support via per-record meta."""

    def test_batch_write_gen_check_success(self, client, cleanup):
        """Per-record gen check succeeds when generation matches."""
        key = ("test", "demo", "bw_gen_ok")
        cleanup.append(key)
        client.put(key, {"val": 1})
        _, meta, _ = client.get(key)
        current_gen = meta.gen

        results = client.batch_write([(key, {"val": 2}, {"gen": current_gen})])
        assert results.batch_records[0].result == 0
        _, _, bins = client.get(key)
        assert bins["val"] == 2

    def test_batch_write_gen_check_mismatch(self, client, cleanup):
        """Per-record gen check fails when generation does not match."""
        key = ("test", "demo", "bw_gen_mismatch")
        cleanup.append(key)
        client.put(key, {"val": 1})

        # stale generation = 999
        results = client.batch_write([(key, {"val": 2}, {"gen": 999})])
        assert results.batch_records[0].result != 0  # GENERATION_ERROR

    def test_batch_write_gen_and_ttl_combined(self, client, cleanup):
        """Gen and TTL can be used together in WriteMeta."""
        key = ("test", "demo", "bw_gen_ttl")
        cleanup.append(key)
        client.put(key, {"val": 1})
        _, meta, _ = client.get(key)
        current_gen = meta.gen

        results = client.batch_write([(key, {"val": 2}, {"gen": current_gen, "ttl": 3600})])
        assert results.batch_records[0].result == 0
        _, meta2, bins = client.get(key)
        assert bins["val"] == 2
        assert meta2.ttl > 0
        assert meta2.ttl <= 3600


class TestBatchRemove:
    def test_batch_remove(self, client):
        keys = [
            ("test", "demo", "batch_rm_1"),
            ("test", "demo", "batch_rm_2"),
        ]

        client.put(keys[0], {"val": 1})
        client.put(keys[1], {"val": 2})

        client.batch_remove(keys)

        for k in keys:
            _, meta = client.exists(k)
            assert meta is None
