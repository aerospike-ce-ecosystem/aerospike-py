"""Edge-case integration tests for batch_write_numpy / batch_read with numpy.

Covers scenarios that prior bugs would have silently corrupted:
- write → read roundtrip verification
- dtype boundary values (i8, i16, i32, u8, u16)
- mixed success/failure in batch_write_numpy (result_code preservation)
- large batch (1000+ records)
- multiple bin types in single dtype
- bytes key roundtrip through write → read
- integer key collision with numpy key_map
- float32 vector embedding write → read roundtrip
- custom key_field names
- overwrite existing records
- concurrent async write → read
"""

import numpy as np

from aerospike_py.numpy_batch import NumpyBatchRecords

NS = "test"
SET = "np_edge"


# ── write → read roundtrip ─────────────────────────────────────────


class TestWriteReadRoundtrip:
    """batch_write_numpy → batch_read with _dtype: data must survive unchanged."""

    def test_basic_int_float_roundtrip(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
        data = np.array(
            [(1, 0.95, 10), (2, 0.87, 20), (3, 0.42, 30)],
            dtype=dtype,
        )
        results = client.batch_write_numpy(data, NS, SET, dtype)
        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0, f"write failed: key={br.key}, result={br.result}"
        keys = [(NS, SET, i) for i in [1, 2, 3]]
        for k in keys:
            cleanup.append(k)

        read_dtype = np.dtype([("score", "f8"), ("count", "i4")])
        read = client.batch_read(keys, _dtype=read_dtype)
        assert isinstance(read, NumpyBatchRecords)
        np.testing.assert_array_equal(read.result_codes, [0, 0, 0])
        np.testing.assert_almost_equal(read.batch_records["score"], [0.95, 0.87, 0.42])
        np.testing.assert_array_equal(read.batch_records["count"], [10, 20, 30])

    def test_bytes_key_roundtrip(self, client, cleanup):
        """Bytes key roundtrip: numpy S10 trailing null padding is trimmed.

        numpy S10 dtype pads b"alice" to b"alice\\x00\\x00\\x00\\x00\\x00",
        but batch_write_numpy trims trailing nulls so the digest matches
        a subsequent lookup using the original unpadded key b"alice".
        """
        dtype = np.dtype([("_key", "S10"), ("val", "i8")])
        names = [b"alice", b"bob", b"charlie"]
        data = np.array(
            [(names[0], 100), (names[1], 200), (names[2], 300)],
            dtype=dtype,
        )
        results = client.batch_write_numpy(data, NS, SET, dtype)
        # Lookup uses the original unpadded keys
        keys = [(NS, SET, name) for name in names]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        # batch_read with unpadded keys must find the records
        read_dtype = np.dtype([("val", "i8")])
        read = client.batch_read(keys, _dtype=read_dtype)
        np.testing.assert_array_equal(read.batch_records["val"], [100, 200, 300])

        # Regular get with unpadded key must also work
        rec = client.get(keys[0])
        assert rec.bins["val"] == 100

    def test_large_batch_1000_records(self, client, cleanup):
        n = 1000
        dtype = np.dtype([("_key", "i4"), ("x", "f8"), ("y", "i4")])
        data = np.zeros(n, dtype=dtype)
        data["_key"] = np.arange(n) + 10000
        data["x"] = np.random.rand(n) * 100
        data["y"] = np.arange(n)

        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, int(10000 + i)) for i in range(n)]
        for k in keys:
            cleanup.append(k)
        failed = [br for br in results.batch_records if br.result != 0]
        assert len(failed) == 0, f"{len(failed)} writes failed out of {n}"

        read_dtype = np.dtype([("x", "f8"), ("y", "i4")])
        read = client.batch_read(keys, _dtype=read_dtype)
        ok = read.result_codes == 0
        assert ok.sum() == n
        np.testing.assert_array_equal(read.batch_records["y"], np.arange(n))
        np.testing.assert_array_almost_equal(read.batch_records["x"], data["x"])

    def test_overwrite_existing_records(self, client, cleanup):
        """Write, then overwrite with new values, then read back."""
        dtype = np.dtype([("_key", "i4"), ("val", "i4")])
        keys = [(NS, SET, 9001), (NS, SET, 9002)]
        for k in keys:
            cleanup.append(k)

        data1 = np.array([(9001, 111), (9002, 222)], dtype=dtype)
        client.batch_write_numpy(data1, NS, SET, dtype)

        data2 = np.array([(9001, 999), (9002, 888)], dtype=dtype)
        results = client.batch_write_numpy(data2, NS, SET, dtype)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read(keys, _dtype=read_dtype)
        np.testing.assert_array_equal(read.batch_records["val"], [999, 888])


# ── dtype boundary values ──────────────────────────────────────────


class TestDtypeBoundaryValues:
    """Test that values at the edge of dtype ranges are preserved correctly."""

    def test_i32_boundary(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("val", "i4")])
        data = np.array(
            [(8001, np.iinfo(np.int32).max), (8002, np.iinfo(np.int32).min), (8003, 0)],
            dtype=dtype,
        )
        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 8001), (NS, SET, 8002), (NS, SET, 8003)]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("val", "i8")])  # read as i8 to avoid truncation
        read = client.batch_read(keys, _dtype=read_dtype)
        assert read.batch_records[0]["val"] == np.iinfo(np.int32).max
        assert read.batch_records[1]["val"] == np.iinfo(np.int32).min
        assert read.batch_records[2]["val"] == 0

    def test_i64_large_values(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("big", "i8")])
        big_val = 2**60
        data = np.array([(8010, big_val), (8011, -big_val)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 8010), (NS, SET, 8011)]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("big", "i8")])
        read = client.batch_read(keys, _dtype=read_dtype)
        assert read.batch_records[0]["big"] == big_val
        assert read.batch_records[1]["big"] == -big_val

    def test_float64_special_values(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("f", "f8")])
        data = np.array(
            [(8020, 1e308), (8021, -1e308), (8022, 1e-300)],
            dtype=dtype,
        )
        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 8020), (NS, SET, 8021), (NS, SET, 8022)]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("f", "f8")])
        read = client.batch_read(keys, _dtype=read_dtype)
        np.testing.assert_almost_equal(read.batch_records[0]["f"], 1e308)
        np.testing.assert_almost_equal(read.batch_records[1]["f"], -1e308)
        assert read.batch_records[2]["f"] != 0.0  # very small but nonzero


# ── batch_write_numpy result_code preservation ──────────────────────


class TestBatchWriteResultCodes:
    """Verify per-record result_code from batch_write_numpy."""

    def test_all_success_result_codes(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("v", "i4")])
        data = np.array([(7001, 1), (7002, 2), (7003, 3)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 7001), (NS, SET, 7002), (NS, SET, 7003)]
        for k in keys:
            cleanup.append(k)

        for br in results.batch_records:
            assert br.result == 0
            assert br.key is not None
            assert br.record is not None
            assert br.record.meta is not None
            assert br.record.meta.gen >= 1

    def test_result_code_has_key_info(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("v", "i4")])
        data = np.array([(7010, 10)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        cleanup.append((NS, SET, 7010))

        br = results.batch_records[0]
        assert br.key is not None
        assert br.key.namespace == NS
        assert br.key.set_name == SET


# ── multiple bin types ─────────────────────────────────────────────


class TestMultipleBinTypes:
    """Write and read multiple bin types in a single batch."""

    def test_mixed_int_float_bytes(self, client, cleanup):
        dim = 4
        vec = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        blob = vec.tobytes()

        dtype_w = np.dtype([("_key", "i4"), ("count", "i4"), ("score", "f8"), ("embedding", f"S{dim * 4}")])
        data = np.array([(6001, 42, 0.99, blob)], dtype=dtype_w)
        results = client.batch_write_numpy(data, NS, SET, dtype_w)
        cleanup.append((NS, SET, 6001))
        assert results.batch_records[0].result == 0

        dtype_r = np.dtype([("count", "i4"), ("score", "f8"), ("embedding", f"S{dim * 4}")])
        read = client.batch_read([(NS, SET, 6001)], _dtype=dtype_r)
        assert read.batch_records[0]["count"] == 42
        np.testing.assert_almost_equal(read.batch_records[0]["score"], 0.99)
        recovered = np.frombuffer(read.batch_records[0]["embedding"], dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, vec)

    def test_many_bins_10(self, client, cleanup):
        """Write 10 different bins and verify all come back."""
        fields = [("_key", "i4")] + [(f"b{i}", "f8") for i in range(10)]
        dtype = np.dtype(fields)
        row = tuple([5001] + [float(i) * 1.1 for i in range(10)])
        data = np.array([row], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        cleanup.append((NS, SET, 5001))
        assert results.batch_records[0].result == 0

        read_fields = [(f"b{i}", "f8") for i in range(10)]
        read_dtype = np.dtype(read_fields)
        read = client.batch_read([(NS, SET, 5001)], _dtype=read_dtype)
        for i in range(10):
            np.testing.assert_almost_equal(read.batch_records[0][f"b{i}"], float(i) * 1.1)


# ── custom key_field ───────────────────────────────────────────────


class TestCustomKeyField:
    def test_custom_key_field_name(self, client, cleanup):
        dtype = np.dtype([("id", "i4"), ("val", "f8")])
        data = np.array([(4001, 3.14), (4002, 2.72)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype, key_field="id")
        keys = [(NS, SET, 4001), (NS, SET, 4002)]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("val", "f8")])
        read = client.batch_read(keys, _dtype=read_dtype)
        np.testing.assert_almost_equal(read.batch_records[0]["val"], 3.14)
        np.testing.assert_almost_equal(read.batch_records[1]["val"], 2.72)


# ── vector embedding write → read ─────────────────────────────────


class TestVectorWriteRead:
    def test_float32_vectors_roundtrip(self, client, cleanup):
        """Write float32 vectors as bytes via batch_write_numpy, read back."""
        dim = 128
        n = 50
        vectors = np.random.rand(n, dim).astype(np.float32)

        blob_size = dim * 4
        dtype_w = np.dtype([("_key", "i4"), ("embedding", f"S{blob_size}"), ("label", "i4")])
        rows = []
        for i in range(n):
            rows.append((3000 + i, vectors[i].tobytes(), i))
        data = np.array(rows, dtype=dtype_w)

        results = client.batch_write_numpy(data, NS, SET, dtype_w)
        keys = [(NS, SET, 3000 + i) for i in range(n)]
        for k in keys:
            cleanup.append(k)
        failed = [br for br in results.batch_records if br.result != 0]
        assert len(failed) == 0

        dtype_r = np.dtype([("embedding", f"S{blob_size}"), ("label", "i4")])
        read = client.batch_read(keys, _dtype=dtype_r)
        assert (read.result_codes == 0).all()
        for i in range(n):
            recovered = np.frombuffer(read.batch_records[i]["embedding"], dtype=np.float32)
            np.testing.assert_array_almost_equal(recovered, vectors[i])
            assert read.batch_records[i]["label"] == i


# ── batch_read with mixed existing/missing after write ─────────────


class TestWriteThenPartialRead:
    def test_read_mix_of_written_and_missing(self, client, cleanup):
        """Write some keys, then batch_read including non-written keys."""
        dtype_w = np.dtype([("_key", "i4"), ("val", "i4")])
        data = np.array([(2001, 10), (2002, 20)], dtype=dtype_w)
        client.batch_write_numpy(data, NS, SET, dtype_w)
        cleanup.extend([(NS, SET, 2001), (NS, SET, 2002)])

        all_keys = [(NS, SET, 2001), (NS, SET, 2002), (NS, SET, 2099)]
        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read(all_keys, _dtype=read_dtype)

        assert read.result_codes[0] == 0
        assert read.result_codes[1] == 0
        assert read.result_codes[2] != 0  # missing
        assert read.batch_records[0]["val"] == 10
        assert read.batch_records[1]["val"] == 20
        assert read.batch_records[2]["val"] == 0  # zero-filled for missing


# ── async write → read ──────────────────────────────────────────────


class TestAsyncWriteReadRoundtrip:
    async def test_async_basic_roundtrip(self, async_client, async_cleanup):
        dtype = np.dtype([("_key", "i4"), ("val", "f8")])
        data = np.array([(1001, 1.11), (1002, 2.22), (1003, 3.33)], dtype=dtype)
        results = await async_client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 1001), (NS, SET, 1002), (NS, SET, 1003)]
        for k in keys:
            async_cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("val", "f8")])
        read = await async_client.batch_read(keys, _dtype=read_dtype)
        np.testing.assert_almost_equal(read.batch_records["val"], [1.11, 2.22, 3.33])

    async def test_async_large_batch_500(self, async_client, async_cleanup):
        n = 500
        dtype = np.dtype([("_key", "i4"), ("x", "f8")])
        data = np.zeros(n, dtype=dtype)
        data["_key"] = np.arange(n) + 20000
        data["x"] = np.arange(n, dtype=np.float64)

        results = await async_client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, int(20000 + i)) for i in range(n)]
        for k in keys:
            async_cleanup.append(k)
        failed = [br for br in results.batch_records if br.result != 0]
        assert len(failed) == 0

        read_dtype = np.dtype([("x", "f8")])
        read = await async_client.batch_read(keys, _dtype=read_dtype)
        assert (read.result_codes == 0).all()
        np.testing.assert_array_almost_equal(read.batch_records["x"], np.arange(n, dtype=np.float64))

    async def test_async_write_result_codes(self, async_client, async_cleanup):
        """Verify async batch_write_numpy returns BatchRecord with result codes."""
        dtype = np.dtype([("_key", "i4"), ("v", "i4")])
        data = np.array([(1101, 1), (1102, 2)], dtype=dtype)
        results = await async_client.batch_write_numpy(data, NS, SET, dtype)
        for k in [(NS, SET, 1101), (NS, SET, 1102)]:
            async_cleanup.append(k)

        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.key is not None


# ── single record edge case ────────────────────────────────────────


class TestSingleRecord:
    def test_single_write_read(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("val", "i8")])
        data = np.array([(99, 42)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        cleanup.append((NS, SET, 99))
        assert len(results.batch_records) == 1
        assert results.batch_records[0].result == 0

        read_dtype = np.dtype([("val", "i8")])
        read = client.batch_read([(NS, SET, 99)], _dtype=read_dtype)
        assert read.batch_records[0]["val"] == 42


# ── integer key with numpy key_map lookup ──────────────────────────


class TestIntegerKeyLookup:
    def test_integer_keys_no_collision(self, client, cleanup):
        """Write with integer keys, then batch_read and lookup via get()."""
        dtype = np.dtype([("_key", "i4"), ("val", "i4")])
        data = np.array([(0, 100), (1, 200), (2, 300)], dtype=dtype)
        results = client.batch_write_numpy(data, NS, SET, dtype)
        keys = [(NS, SET, 0), (NS, SET, 1), (NS, SET, 2)]
        for k in keys:
            cleanup.append(k)
        for br in results.batch_records:
            assert br.result == 0

        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read(keys, _dtype=read_dtype)
        assert read.get(0)["val"] == 100
        assert read.get(1)["val"] == 200
        assert read.get(2)["val"] == 300

    def test_negative_integer_keys(self, client, cleanup):
        key = (NS, SET, -42)
        cleanup.append(key)
        client.put(key, {"val": 777})

        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read([key], _dtype=read_dtype)
        assert read.result_codes[0] == 0
        assert read.batch_records[0]["val"] == 777


# ── meta verification after write ──────────────────────────────────


class TestMetaAfterWrite:
    def test_gen_is_1_after_fresh_write(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("val", "i4")])
        data = np.array([(8100, 1)], dtype=dtype)
        client.batch_write_numpy(data, NS, SET, dtype)
        cleanup.append((NS, SET, 8100))

        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read([(NS, SET, 8100)], _dtype=read_dtype)
        assert read.meta[0]["gen"] >= 1

    def test_gen_increments_on_overwrite(self, client, cleanup):
        dtype = np.dtype([("_key", "i4"), ("val", "i4")])
        cleanup.append((NS, SET, 8101))

        data1 = np.array([(8101, 1)], dtype=dtype)
        client.batch_write_numpy(data1, NS, SET, dtype)

        data2 = np.array([(8101, 2)], dtype=dtype)
        client.batch_write_numpy(data2, NS, SET, dtype)

        read_dtype = np.dtype([("val", "i4")])
        read = client.batch_read([(NS, SET, 8101)], _dtype=read_dtype)
        assert read.meta[0]["gen"] >= 2
        assert read.batch_records[0]["val"] == 2
