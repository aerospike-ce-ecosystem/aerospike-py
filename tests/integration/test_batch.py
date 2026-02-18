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
        assert len(result.batch_records) == 3
        for br in result.batch_records:
            assert br.result == 0
            assert br.record is not None
            _, meta, bins = br.record
            assert meta is not None
            assert meta["gen"] >= 1
            assert "a" in bins

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
        assert len(result.batch_records) == 2
        for br in result.batch_records:
            assert br.result == 0
            _, meta, bins = br.record
            assert meta is not None
            assert "a" in bins
            assert "c" in bins

    def test_batch_read_exists(self, client, cleanup):
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
        assert len(result.batch_records) == 3
        assert result.batch_records[0].result == 0
        assert result.batch_records[1].result == 0
        assert result.batch_records[2].result == 2  # KEY_NOT_FOUND

    def test_batch_read_with_missing(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_get_exists"),
            ("test", "demo", "batch_get_missing"),
        ]
        cleanup.append(keys[0])

        client.put(keys[0], {"val": 1})

        result = client.batch_read(keys)
        assert len(result.batch_records) == 2
        # First key exists
        br0 = result.batch_records[0]
        assert br0.result == 0
        assert br0.record is not None
        _, meta0, bins0 = br0.record
        assert meta0 is not None
        assert bins0["val"] == 1
        # Second key missing
        br1 = result.batch_records[1]
        assert br1.result == 2  # KEY_NOT_FOUND
        assert br1.record is None


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
        assert len(results) == 2
        _, _, bins0 = results[0]
        _, _, bins1 = results[1]
        # Batch operate returns multi-op results as list per bin
        counter0 = bins0["counter"]
        counter1 = bins1["counter"]
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
        assert len(results) == 3

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
        assert len(results) == 2

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
        assert len(results) == 2

        # First record should succeed
        _, meta0, bins0 = results[0]
        assert meta0 is not None

        # Second record should fail (None meta/bins due to type mismatch)
        _, meta1, bins1 = results[1]
        assert meta1 is None
        assert bins1 is None

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
        assert len(results) == 2
        for rec in results:
            _, meta, bins = rec
            assert meta is not None
            val = bins["val"]
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
        assert len(results) == n

        # Verify all written
        read_result = client.batch_read(keys)
        assert len(read_result.batch_records) == n
        for br in read_result.batch_records:
            assert br.result == 0
            assert br.record is not None


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
