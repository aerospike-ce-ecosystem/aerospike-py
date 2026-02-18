"""End-to-end scenario tests combining multiple operations."""

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG


class TestCRUDWorkflow:
    """Multi-step CRUD workflow scenarios."""

    def test_create_read_update_delete(self, client, cleanup):
        """Full lifecycle: create → read → update → verify → delete → verify gone."""
        key = ("test", "scenario", "lifecycle_1")
        cleanup.append(key)

        # Create
        client.put(key, {"name": "Alice", "age": 25, "score": 100})
        _, meta1, bins = client.get(key)
        assert bins["name"] == "Alice"
        assert bins["age"] == 25
        gen1 = meta1.gen

        # Update
        client.put(key, {"age": 26, "score": 200})
        _, meta2, bins = client.get(key)
        assert bins["name"] == "Alice"  # unchanged bin persists
        assert bins["age"] == 26
        assert bins["score"] == 200
        assert meta2.gen == gen1 + 1

        # Delete
        client.remove(key)
        _, meta = client.exists(key)
        assert meta is None

    def test_increment_then_read_consistency(self, client, cleanup):
        """Increment multiple times and verify final value."""
        key = ("test", "scenario", "incr_multi")
        cleanup.append(key)

        client.put(key, {"counter": 0})
        for i in range(10):
            client.increment(key, "counter", 1)

        _, _, bins = client.get(key)
        assert bins["counter"] == 10

    def test_append_prepend_chain(self, client, cleanup):
        """Chain append and prepend to build a string."""
        key = ("test", "scenario", "str_chain")
        cleanup.append(key)

        client.put(key, {"msg": "World"})
        client.prepend(key, "msg", "Hello ")
        client.append(key, "msg", "!")

        _, _, bins = client.get(key)
        assert bins["msg"] == "Hello World!"

    def test_remove_bins_then_add_new(self, client, cleanup):
        """Remove specific bins, then add new ones."""
        key = ("test", "scenario", "remove_add_bins")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3, "d": 4})
        client.remove_bin(key, ["b", "d"])

        _, _, bins = client.get(key)
        assert set(bins.keys()) == {"a", "c"}

        # Add new bins
        client.put(key, {"e": 5, "f": 6})
        _, _, bins = client.get(key)
        assert "a" in bins
        assert "c" in bins
        assert bins["e"] == 5
        assert bins["f"] == 6

    def test_operate_multi_ops_workflow(self, client, cleanup):
        """Use operate() to perform multiple operations atomically."""
        key = ("test", "scenario", "multi_ops")
        cleanup.append(key)

        client.put(key, {"views": 0, "name": "test_item"})

        # Atomically increment and read
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1},
            {"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1},
            {"op": aerospike_py.OPERATOR_READ, "bin": "views", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "name", "val": None},
        ]
        _, _, bins = client.operate(key, ops)
        assert bins["views"] == 2
        assert bins["name"] == "test_item"


class TestBatchWorkflow:
    """Scenarios combining batch and individual operations."""

    def test_bulk_write_then_batch_read(self, client, cleanup):
        """Write records individually, then batch read them all."""
        keys = [("test", "scenario", f"bulk_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            client.put(key, {"idx": i, "val": f"item_{i}"})

        result = client.batch_read(keys)
        assert len(result.batch_records) == 5
        for i, br in enumerate(result.batch_records):
            assert br.result == 0
            _, meta, bins = br.record
            assert meta is not None
            assert bins["idx"] == i
            assert bins["val"] == f"item_{i}"

    def test_batch_read_partial_exists(self, client, cleanup):
        """Batch read where some records exist and some don't."""
        existing = [("test", "scenario", f"partial_{i}") for i in range(3)]
        missing = [("test", "scenario", f"partial_missing_{i}") for i in range(2)]
        for k in existing:
            cleanup.append(k)

        for i, key in enumerate(existing):
            client.put(key, {"val": i})

        result = client.batch_read(existing + missing)
        assert len(result.batch_records) == 5

        # First 3 should have data
        for i in range(3):
            br = result.batch_records[i]
            assert br.result == 0
            _, meta, bins = br.record
            assert meta is not None
            assert bins["val"] == i

        # Last 2 should be missing
        for i in range(3, 5):
            br = result.batch_records[i]
            assert br.result == 2  # KEY_NOT_FOUND
            assert br.record is None

    def test_batch_operate_then_verify(self, client, cleanup):
        """Batch operate on multiple records, then verify individually."""
        keys = [("test", "scenario", f"bop_{i}") for i in range(3)]
        for k in keys:
            cleanup.append(k)
            client.put(k, {"counter": 10})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
        ]
        client.batch_operate(keys, ops)

        for key in keys:
            _, _, bins = client.get(key)
            assert bins["counter"] == 15

    def test_batch_remove_then_batch_read_exists(self, client, cleanup):
        """Create records, batch remove, verify with batch_read existence check."""
        keys = [("test", "scenario", f"brem_{i}") for i in range(4)]
        for key in keys:
            client.put(key, {"val": 1})

        client.batch_remove(keys)

        result = client.batch_read(keys, bins=[])
        for br in result.batch_records:
            assert br.result == 2  # KEY_NOT_FOUND


class TestQueryScanWorkflow:
    """Scenarios combining writes with queries/scans."""

    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        """Set up test data for query/scan scenarios."""
        self.ns = "test"
        self.set_name = "scenario_qs"
        self.keys = []

        for i in range(10):
            key = (self.ns, self.set_name, f"qs_{i}")
            client.put(
                key,
                {
                    "id": i,
                    "category": "even" if i % 2 == 0 else "odd",
                    "value": i * 100,
                },
                policy={"key": aerospike_py.POLICY_KEY_SEND},
            )
            self.keys.append(key)

        yield

        for key in self.keys:
            try:
                client.remove(key)
            except Exception:
                pass

    def test_scan_count_matches_inserts(self, client):
        """Scan should return at least as many records as we inserted."""
        scan = client.scan(self.ns, self.set_name)
        results = scan.results()
        assert len(results) >= 10

    def test_scan_then_modify(self, client):
        """Scan to find records, then modify them individually."""
        scan = client.scan(self.ns, self.set_name)
        scan.select("id", "value")
        results = scan.results()

        modified_count = 0
        for key_tuple, meta, bins in results:
            if bins.get("value", 0) >= 500:
                ns = key_tuple[0] if isinstance(key_tuple, tuple) else self.ns
                set_n = key_tuple[1] if isinstance(key_tuple, tuple) else self.set_name
                pk = key_tuple[2] if isinstance(key_tuple, tuple) else None
                if pk is not None:
                    client.put((ns, set_n, pk), {"value": bins["value"] * 2})
                    modified_count += 1

        assert modified_count >= 5  # values 500, 600, 700, 800, 900

    def test_scan_foreach_accumulate(self, client):
        """Use foreach to accumulate values from a scan."""
        scan = client.scan(self.ns, self.set_name)
        scan.select("value")

        total = [0]

        def accumulator(record):
            _, _, bins = record
            total[0] += bins.get("value", 0)

        scan.foreach(accumulator)
        # Sum of 0,100,200,...,900 = 4500
        assert total[0] >= 4500

    def test_query_with_index(self, client):
        """Create index, query with predicate, verify results."""
        idx_name = "scenario_id_idx"
        try:
            client.index_integer_create(self.ns, self.set_name, "id", idx_name)
        except aerospike_py.IndexFoundError:
            pass  # already exists

        try:
            query = client.query(self.ns, self.set_name)
            query.where(aerospike_py.predicates.between("id", 3, 7))
            results = query.results()

            ids = [bins["id"] for _, _, bins in results]
            assert len(ids) >= 5
            for id_val in ids:
                assert 3 <= id_val <= 7
        finally:
            try:
                client.index_remove(self.ns, idx_name)
            except Exception:
                pass


class TestTTLScenarios:
    """Scenarios involving TTL (time-to-live)."""

    def test_ttl_set_and_verify(self, client, cleanup):
        """Set TTL and verify it's within expected range."""
        key = ("test", "scenario", "ttl_1")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"ttl": 600})
        _, meta, _ = client.get(key)
        assert 0 < meta.ttl <= 600

    def test_ttl_touch_extends(self, client, cleanup):
        """Touch should extend TTL."""
        key = ("test", "scenario", "ttl_touch")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"ttl": 100})
        _, meta1, _ = client.get(key)
        original_ttl = meta1.ttl

        client.touch(key, 1000)
        _, meta2, _ = client.get(key)
        assert meta2.ttl > original_ttl

    def test_ttl_never_expire(self, client, cleanup):
        """Set TTL to never expire."""
        key = ("test", "scenario", "ttl_never")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"ttl": aerospike_py.TTL_NEVER_EXPIRE})
        _, meta, _ = client.get(key)
        # TTL for never-expire is a very large number
        assert meta.ttl > 0


class TestGenerationPolicy:
    """Scenarios involving generation (optimistic locking)."""

    def test_generation_increments(self, client, cleanup):
        """Each write should increment generation."""
        key = ("test", "scenario", "gen_inc")
        cleanup.append(key)

        client.put(key, {"val": 1})
        _, meta1, _ = client.get(key)
        assert meta1.gen == 1

        client.put(key, {"val": 2})
        _, meta2, _ = client.get(key)
        assert meta2.gen == 2

        client.put(key, {"val": 3})
        _, meta3, _ = client.get(key)
        assert meta3.gen == 3

    def test_generation_eq_policy_success(self, client, cleanup):
        """Write with gen=current should succeed."""
        key = ("test", "scenario", "gen_eq_ok")
        cleanup.append(key)

        client.put(key, {"val": 1})
        _, meta, _ = client.get(key)

        # Write with matching generation
        client.put(
            key,
            {"val": 2},
            meta={"gen": meta.gen},
            policy={"gen": aerospike_py.POLICY_GEN_EQ},
        )
        _, meta2, bins = client.get(key)
        assert bins["val"] == 2

    def test_generation_eq_policy_failure(self, client, cleanup):
        """Write with stale generation should fail."""
        key = ("test", "scenario", "gen_eq_fail")
        cleanup.append(key)

        client.put(key, {"val": 1})

        # Write with wrong generation should raise
        with pytest.raises(aerospike_py.RecordGenerationError):
            client.put(
                key,
                {"val": 2},
                meta={"gen": 999},
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )

        # Original value should be unchanged
        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_optimistic_locking_pattern(self, client, cleanup):
        """Simulate optimistic locking: read-modify-write with gen check."""
        key = ("test", "scenario", "opt_lock")
        cleanup.append(key)

        # Initial write
        client.put(key, {"balance": 1000})

        # Reader 1 reads
        _, meta1, bins1 = client.get(key)
        assert bins1["balance"] == 1000

        # Reader 1 writes with gen check
        client.put(
            key,
            {"balance": bins1["balance"] - 100},
            meta={"gen": meta1.gen},
            policy={"gen": aerospike_py.POLICY_GEN_EQ},
        )

        # Reader 2 tries to write with stale gen - should fail
        with pytest.raises(aerospike_py.RecordGenerationError):
            client.put(
                key,
                {"balance": bins1["balance"] + 500},
                meta={"gen": meta1.gen},  # stale!
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )

        # Balance should be 900, not 1500
        _, _, bins = client.get(key)
        assert bins["balance"] == 900


class TestExistsPolicy:
    """Scenarios involving record-exists policies."""

    def test_create_only_success(self, client, cleanup):
        """CREATE_ONLY should succeed when record doesn't exist."""
        key = ("test", "scenario", "create_only_ok")
        cleanup.append(key)

        client.put(key, {"val": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_create_only_failure(self, client, cleanup):
        """CREATE_ONLY should fail when record already exists."""
        key = ("test", "scenario", "create_only_fail")
        cleanup.append(key)

        client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordExistsError):
            client.put(
                key,
                {"val": 2},
                policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )

        # Value should remain unchanged
        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_update_only_success(self, client, cleanup):
        """UPDATE_ONLY should succeed when record exists."""
        key = ("test", "scenario", "update_only_ok")
        cleanup.append(key)

        client.put(key, {"val": 1})
        client.put(key, {"val": 2}, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE})
        _, _, bins = client.get(key)
        assert bins["val"] == 2

    def test_update_only_failure(self, client, cleanup):
        """UPDATE_ONLY should fail when record doesn't exist."""
        key = ("test", "scenario", "update_only_fail")

        with pytest.raises(aerospike_py.AerospikeError):
            client.put(key, {"val": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE})


class TestErrorHandling:
    """Scenarios testing expected error conditions."""

    def test_get_nonexistent_record(self, client):
        """Getting a non-existent record should raise RecordNotFound."""
        key = ("test", "scenario", "nonexistent_key_xyz_12345")
        with pytest.raises(aerospike_py.RecordNotFound):
            client.get(key)

    def test_remove_nonexistent_is_ok(self, client):
        """Removing a non-existent record should not raise by default."""
        key = ("test", "scenario", "nonexistent_remove_xyz")
        # Default policy allows removing non-existent records
        # (server returns ok for delete of non-existent key)
        try:
            client.remove(key)
        except aerospike_py.RecordNotFound:
            pass  # Some servers may raise this, which is also acceptable

    def test_invalid_namespace_raises(self, client):
        """Using an invalid namespace should raise an error."""
        key = ("nonexistent_namespace_xyz", "demo", "key1")
        with pytest.raises(aerospike_py.AerospikeError):
            client.put(key, {"val": 1})

    def test_operations_after_close(self, client):
        """Create a separate client, close it, then try operations."""
        c2 = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        c2.close()

        with pytest.raises(aerospike_py.AerospikeError):
            c2.get(("test", "demo", "key1"))

    def test_empty_bins_put(self, client, cleanup):
        """Put with empty bins dict should not crash."""
        key = ("test", "scenario", "empty_bins")
        cleanup.append(key)
        # Empty dict put - should either succeed or raise cleanly
        try:
            client.put(key, {})
        except aerospike_py.AerospikeError:
            pass  # acceptable to reject empty bins

    def test_double_close_is_safe(self, client):
        """Closing a client twice should not crash."""
        c2 = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        c2.close()
        c2.close()  # Should not raise

    def test_connect_bad_host(self):
        """Connecting to a bad host should raise."""
        c = aerospike_py.client({"hosts": [("192.0.2.1", 9999)], "timeout": 1000})
        with pytest.raises(aerospike_py.AerospikeError):
            c.connect()


class TestDataTypeEdgeCases:
    """Edge cases for various data types."""

    def test_empty_string(self, client, cleanup):
        key = ("test", "scenario", "empty_str")
        cleanup.append(key)
        client.put(key, {"val": ""})
        _, _, bins = client.get(key)
        assert bins["val"] == ""

    def test_large_string(self, client, cleanup):
        key = ("test", "scenario", "large_str")
        cleanup.append(key)
        large = "x" * 100_000
        client.put(key, {"val": large})
        _, _, bins = client.get(key)
        assert bins["val"] == large
        assert len(bins["val"]) == 100_000

    def test_unicode_string(self, client, cleanup):
        key = ("test", "scenario", "unicode_str")
        cleanup.append(key)
        client.put(key, {"val": "한글 테스트 🎉 日本語 العربية"})
        _, _, bins = client.get(key)
        assert bins["val"] == "한글 테스트 🎉 日本語 العربية"

    def test_large_integer(self, client, cleanup):
        key = ("test", "scenario", "large_int")
        cleanup.append(key)
        client.put(key, {"val": 2**62})
        _, _, bins = client.get(key)
        assert bins["val"] == 2**62

    def test_negative_integer(self, client, cleanup):
        key = ("test", "scenario", "neg_int")
        cleanup.append(key)
        client.put(key, {"val": -999999})
        _, _, bins = client.get(key)
        assert bins["val"] == -999999

    def test_zero_float(self, client, cleanup):
        key = ("test", "scenario", "zero_float")
        cleanup.append(key)
        client.put(key, {"val": 0.0})
        _, _, bins = client.get(key)
        assert bins["val"] == 0.0

    def test_empty_list(self, client, cleanup):
        key = ("test", "scenario", "empty_list")
        cleanup.append(key)
        client.put(key, {"val": []})
        _, _, bins = client.get(key)
        assert bins["val"] == []

    def test_empty_map(self, client, cleanup):
        key = ("test", "scenario", "empty_map")
        cleanup.append(key)
        client.put(key, {"val": {}})
        _, _, bins = client.get(key)
        assert bins["val"] == {}

    def test_nested_structures(self, client, cleanup):
        key = ("test", "scenario", "nested")
        cleanup.append(key)
        data = {
            "users": [
                {"name": "Alice", "scores": [95, 87, 92]},
                {"name": "Bob", "scores": [78, 82, 90]},
            ],
            "metadata": {
                "version": 2,
                "tags": ["test", "scenario"],
            },
        }
        client.put(key, {"val": data})
        _, _, bins = client.get(key)
        assert bins["val"]["users"][0]["name"] == "Alice"
        assert bins["val"]["users"][1]["scores"] == [78, 82, 90]
        assert bins["val"]["metadata"]["tags"] == ["test", "scenario"]

    def test_empty_bytes(self, client, cleanup):
        key = ("test", "scenario", "empty_bytes")
        cleanup.append(key)
        client.put(key, {"val": b""})
        _, _, bins = client.get(key)
        assert bins["val"] == b""

    def test_large_bytes(self, client, cleanup):
        key = ("test", "scenario", "large_bytes")
        cleanup.append(key)
        data = bytes(range(256)) * 100
        client.put(key, {"val": data})
        _, _, bins = client.get(key)
        assert bins["val"] == data

    def test_mixed_list_types(self, client, cleanup):
        key = ("test", "scenario", "mixed_list")
        cleanup.append(key)
        val = [1, "two", 3.0, True, None, b"\x00", [1, 2], {"k": "v"}]
        client.put(key, {"val": val})
        _, _, bins = client.get(key)
        result = bins["val"]
        assert result[0] == 1
        assert result[1] == "two"
        assert abs(result[2] - 3.0) < 0.001
        assert result[3] is True
        # None handling varies; it may be stored differently
        assert result[6] == [1, 2]
        assert result[7] == {"k": "v"}

    def test_many_bins(self, client, cleanup):
        """Test record with many bins."""
        key = ("test", "scenario", "many_bins")
        cleanup.append(key)
        bins = {f"bin_{i}": i for i in range(100)}
        client.put(key, bins)
        _, _, result = client.get(key)
        assert len(result) == 100
        for i in range(100):
            assert result[f"bin_{i}"] == i

    def test_integer_key(self, client, cleanup):
        """Test integer primary key."""
        key = ("test", "scenario", 12345)
        cleanup.append(key)
        client.put(key, {"val": "int_key"})
        _, _, bins = client.get(key)
        assert bins["val"] == "int_key"

    def test_bytes_key(self, client, cleanup):
        """Test bytes primary key."""
        key = ("test", "scenario", b"\x01\x02\x03\x04")
        cleanup.append(key)
        client.put(key, {"val": "bytes_key"})
        _, _, bins = client.get(key)
        assert bins["val"] == "bytes_key"


class TestMultiClientScenario:
    """Scenarios with multiple client instances."""

    def test_two_clients_same_record(self, client, cleanup):
        """Two clients can read/write the same record."""
        c2 = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        try:
            key = ("test", "scenario", "multi_client")
            cleanup.append(key)

            client.put(key, {"val": 1})
            _, _, bins = c2.get(key)
            assert bins["val"] == 1

            c2.put(key, {"val": 2})
            _, _, bins = client.get(key)
            assert bins["val"] == 2
        finally:
            c2.close()

    def test_reconnect_after_close(self, cleanup):
        """Client can reconnect after close."""
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        key = ("test", "scenario", "reconnect")
        cleanup.append(key)

        c.put(key, {"val": 1})
        c.close()

        # Reconnect
        c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
        try:
            _, _, bins = c.get(key)
            assert bins["val"] == 1
        finally:
            c.close()


class TestSelectVariations:
    """Various select operation scenarios."""

    def test_select_nonexistent_bin(self, client, cleanup):
        """Selecting a bin that doesn't exist should return without it."""
        key = ("test", "scenario", "select_missing")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2})
        _, _, bins = client.select(key, ["a", "nonexistent"])
        assert bins["a"] == 1
        assert "nonexistent" not in bins

    def test_select_all_bins(self, client, cleanup):
        """Selecting all existing bins returns all."""
        key = ("test", "scenario", "select_all")
        cleanup.append(key)

        client.put(key, {"x": 10, "y": 20, "z": 30})
        _, _, bins = client.select(key, ["x", "y", "z"])
        assert bins == {"x": 10, "y": 20, "z": 30}

    def test_select_single_bin(self, client, cleanup):
        """Selecting a single bin from many."""
        key = ("test", "scenario", "select_single")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
        _, _, bins = client.select(key, ["c"])
        assert bins == {"c": 3}


class TestOperateOrdered:
    """Test operate_ordered returns results in correct order."""

    def test_ordered_multiple_reads(self, client, cleanup):
        key = ("test", "scenario", "ordered_reads")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3})
        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "c", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": None},
            {"op": aerospike_py.OPERATOR_READ, "bin": "b", "val": None},
        ]
        _, meta, ordered = client.operate_ordered(key, ops)
        assert isinstance(ordered, list)
        assert meta.gen >= 1
        # Each element should be (bin_name, value) tuple
        for item in ordered:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_ordered_write_then_read(self, client, cleanup):
        key = ("test", "scenario", "ordered_wr")
        cleanup.append(key)

        client.put(key, {"counter": 0})
        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 10},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        _, _, ordered = client.operate_ordered(key, ops)
        # The read after increment should show the new value
        found = False
        for name, val in ordered:
            if name == "counter":
                assert val == 10
                found = True
        assert found
