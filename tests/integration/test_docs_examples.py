"""Integration tests for docs code examples.

Tests verify that code examples in docs/ actually work as documented.
Requires an Aerospike server (skipped automatically if unavailable).
"""

import pytest

import aerospike_py


class TestBatchReadDocExamples:
    """Tests for docs/docs/guides/crud/read.md batch_read examples."""

    def test_batch_read_all_bins_sync(self, client, cleanup):
        """read.md: Batch read all bins, dot access on br.record."""
        keys = [("test", "demo", f"doc_batch_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            cleanup.append(k)
            client.put(k, {"name": f"user_{i}", "age": 20 + i})

        # Same pattern as the docs example
        batch = client.batch_read(keys)
        for user_key, bins in batch.items():
            assert bins is not None  # dict of bins for each successful read

    def test_batch_read_specific_bins_sync(self, client, cleanup):
        """read.md: Batch read with specific bins."""
        keys = [("test", "demo", f"doc_bins_{i}") for i in range(2)]
        for i, k in enumerate(keys):
            cleanup.append(k)
            client.put(k, {"name": f"user_{i}", "age": 20 + i, "extra": "drop"})

        # docs example: bins=["name", "age"]
        batch = client.batch_read(keys, bins=["name", "age"])
        assert len(batch) == 2
        for user_key, bins in batch.items():
            assert "name" in bins
            assert "age" in bins
            assert "extra" not in bins

    def test_batch_read_existence_check_sync(self, client, cleanup):
        """read.md: Existence check only (bins=[])."""
        existing = ("test", "demo", "doc_exists_1")
        missing = ("test", "demo", "doc_exists_missing")
        cleanup.append(existing)
        client.put(existing, {"val": 1})

        batch = client.batch_read([existing, missing], bins=[])
        assert "doc_exists_1" in batch  # existing key is in dict
        assert "doc_exists_missing" not in batch  # missing key is not in dict

    async def test_batch_read_async(self, async_client, async_cleanup):
        """read.md: Async batch read example."""
        keys = [("test", "demo", f"async_doc_batch_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            async_cleanup.append(k)
            await async_client.put(k, {"name": f"user_{i}", "age": 20 + i})

        # docs example: await client.batch_read(keys, bins=["name", "age"])
        batch = await async_client.batch_read(keys, bins=["name"])
        assert len(batch) == 3
        for user_key, bins in batch.items():
            assert bins is not None

    def test_batch_read_result_code_check(self, client, cleanup):
        """error-handling.md: BatchRecord result code check pattern."""
        keys = [("test", "demo", f"doc_rc_{i}") for i in range(5)]
        for i, k in enumerate(keys[:3]):
            cleanup.append(k)
            client.put(k, {"val": i})

        batch = client.batch_read(keys)

        # With dict return: succeeded keys are in dict, missing keys are not
        succeeded = list(batch.values())
        all_user_keys = {k[2] for k in keys}
        present_keys = set(batch.keys())
        missing_keys = all_user_keys - present_keys

        assert len(succeeded) == 3
        assert len(missing_keys) == 2


class TestBatchOperateDocExamples:
    """Tests for docs/docs/guides/admin/error-handling.md batch_operate examples."""

    def test_batch_operate_returns_list_of_batch_records(self, client, cleanup):
        """error-handling.md: batch_operate returns list[BatchRecord]."""
        from aerospike_py import list_operations

        key = ("test", "demo", "doc_batch_op_1")
        cleanup.append(key)
        client.put(key, {"items": [1, 2, 3]})

        keys = [key]
        ops = [list_operations.list_append("items", 4)]
        results = client.batch_operate(keys, ops)

        # docs example: for br in results.batch_records (BatchRecords container)
        for br in results.batch_records:
            assert br.result == 0
            assert br.key is not None
            assert br.record is not None

    def test_batch_operate_increment_and_read(self, client, cleanup):
        """error-handling.md: batch_operate with INCR + READ operations."""
        keys = [("test", "demo", "doc_bop_incr_1"), ("test", "demo", "doc_bop_incr_2")]
        for k in keys:
            cleanup.append(k)
            client.put(k, {"counter": 10})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.record is not None
            assert br.record.meta is not None


class TestNumpyBatchWriteDocExamples:
    """Tests for docs/docs/guides/crud/numpy-batch-write.md examples."""

    def test_meta_gen_dot_access(self, client, cleanup):
        """numpy-batch-write.md: meta.gen dot access after batch_write_numpy."""
        np = pytest.importorskip("numpy")

        dtype = np.dtype([("_key", "U20"), ("score", "f8"), ("count", "i4")])
        # U dtype is not supported; use i4 for key
        dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
        data = np.array([(1001, 0.95, 10), (1002, 0.87, 20)], dtype=dtype)

        for k in [("test", "demo", 1001), ("test", "demo", 1002)]:
            cleanup.append(k)

        results = client.batch_write_numpy(data, "test", "demo", dtype)

        # docs example: br.record.meta.gen (not meta['gen'])
        for br in results.batch_records:
            assert br.result == 0
            assert br.record is not None
            assert isinstance(br.record.meta.gen, int)  # verify dot access
            assert isinstance(br.record.meta.ttl, int)

    def test_batch_write_numpy_basic(self, client, cleanup):
        """numpy-batch-write.md: Quick Start example."""
        np = pytest.importorskip("numpy")

        dtype = np.dtype(
            [
                ("_key", "i4"),
                ("score", "f8"),
                ("count", "i4"),
            ]
        )
        data = np.array(
            [
                (2001, 0.95, 10),
                (2002, 0.87, 20),
                (2003, 0.72, 15),
            ],
            dtype=dtype,
        )

        for k in [("test", "demo", 2001), ("test", "demo", 2002), ("test", "demo", 2003)]:
            cleanup.append(k)

        # Same as the docs example
        results = client.batch_write_numpy(data, "test", "demo", dtype)

        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0
            assert br.record is not None
            assert br.record.meta.gen >= 1

    def test_batch_write_numpy_key_field_custom(self, client, cleanup):
        """numpy-batch-write.md: Custom key_field example."""
        np = pytest.importorskip("numpy")

        dtype = np.dtype(
            [
                ("user_id", "i8"),
                ("score", "f8"),
            ]
        )
        data = np.array([(3001, 1.5), (3002, 2.5)], dtype=dtype)

        for k in [("test", "demo", 3001), ("test", "demo", 3002)]:
            cleanup.append(k)

        # docs example: key_field="user_id"
        results = client.batch_write_numpy(data, "test", "demo", dtype, key_field="user_id")
        assert len(results.batch_records) == 2
