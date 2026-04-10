"""Integration tests for async numpy batch_read (requires Aerospike server)."""

import numpy as np
import pytest

from aerospike_py.numpy_batch import NumpyBatchRecords

NS = "test"
SET = "async_np_batch"


@pytest.fixture
async def cleanup(async_client):
    keys = []
    yield keys
    for key in keys:
        try:
            await async_client.remove(key)
        except Exception:
            pass


# ── Basic numeric type conversion ──────────────────────────────


class TestAsyncNumericBatchRead:
    async def test_int_float_batch(self, async_client, cleanup):
        """async batch_read int64, float64 bins with _dtype."""
        keys = [(NS, SET, f"num_{i}") for i in range(5)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            await async_client.put(key, {"temperature": 20.0 + i * 0.5, "reading_id": i})

        dtype = np.dtype([("temperature", "f8"), ("reading_id", "i4")])
        result = await async_client.batch_read(keys, _dtype=dtype)

        assert isinstance(result, NumpyBatchRecords)
        assert len(result.batch_records) == 5
        assert result.batch_records.dtype == dtype

        for i in range(5):
            np.testing.assert_almost_equal(result.batch_records[i]["temperature"], 20.0 + i * 0.5)
            assert result.batch_records[i]["reading_id"] == i

    async def test_result_codes(self, async_client, cleanup):
        """result_codes should all be 0 for successful records."""
        keys = [(NS, SET, f"rc_{i}") for i in range(3)]
        for key in keys:
            cleanup.append(key)
            await async_client.put(key, {"val": 1})

        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read(keys, _dtype=dtype)

        np.testing.assert_array_equal(result.result_codes, [0, 0, 0])

    async def test_without_dtype(self, async_client, cleanup):
        """Returns dict when _dtype=None."""
        key = (NS, SET, "nodtype_1")
        cleanup.append(key)
        await async_client.put(key, {"x": 1})

        result = await async_client.batch_read([key])
        assert isinstance(result, dict)


# ── meta (gen, ttl) verification ───────────────────────────────


class TestAsyncMeta:
    async def test_gen_increments(self, async_client, cleanup):
        """Verify gen >= 2 after two puts."""
        key = (NS, SET, "meta_gen")
        cleanup.append(key)
        await async_client.put(key, {"val": 1})
        await async_client.put(key, {"val": 2})

        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read([key], _dtype=dtype)

        assert result.meta[0]["gen"] >= 2

    async def test_ttl_nonzero(self, async_client, cleanup):
        """Verify ttl > 0 for a record with TTL set."""
        key = (NS, SET, "meta_ttl")
        cleanup.append(key)
        await async_client.put(key, {"val": 1}, meta={"ttl": 600})

        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read([key], _dtype=dtype)

        assert result.meta[0]["ttl"] > 0


# ── Key-based lookup (get method) ──────────────────────────────


class TestAsyncGetByKey:
    async def test_get_by_key(self, async_client, cleanup):
        """Lookup by primary_key using get()."""
        keys = [(NS, SET, f"get_{i}") for i in range(3)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            await async_client.put(key, {"val": (i + 1) * 10})

        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read(keys, _dtype=dtype)

        assert result.get("get_0")["val"] == 10
        assert result.get("get_1")["val"] == 20
        assert result.get("get_2")["val"] == 30


# ── Missing record handling ─────────────────────────────────────


class TestAsyncMissingRecord:
    async def test_nonexistent_key_zeroed(self, async_client, cleanup):
        """Non-existent key results in zero/empty value with result_code != 0."""
        existing = (NS, SET, "exist_1")
        missing = (NS, SET, "nonexistent_xyz")
        cleanup.append(existing)
        await async_client.put(existing, {"val": 42})

        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read([existing, missing], _dtype=dtype)

        assert result.result_codes[0] == 0
        assert result.result_codes[1] != 0
        assert result.batch_records[0]["val"] == 42
        assert result.batch_records[1]["val"] == 0


# ── bytes blob store/read ──────────────────────────────────────


class TestAsyncBytesBlob:
    async def test_bytes_blob_roundtrip(self, async_client, cleanup):
        """Store bytes blob and read back via async batch_read."""
        key = (NS, SET, "blob_1")
        cleanup.append(key)
        raw = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        await async_client.put(key, {"data": raw, "score": 0.5})

        dtype = np.dtype([("data", "S8"), ("score", "f4")])
        result = await async_client.batch_read([key], _dtype=dtype)

        assert result.batch_records[0]["data"] == raw
        np.testing.assert_almost_equal(result.batch_records[0]["score"], 0.5, decimal=5)


# ── vector embedding use cases ─────────────────────────────────


class TestAsyncVectorBatch:
    async def test_multiple_vectors_batch(self, async_client, cleanup):
        """Read multiple vectors at once via async batch_read."""
        dim = 4
        n = 10
        vectors = [np.random.rand(dim).astype(np.float32) for _ in range(n)]

        keys = [(NS, SET, f"mvec_{i}") for i in range(n)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            await async_client.put(key, {"embedding": vectors[i].tobytes(), "label": i})

        blob_size = dim * 4
        dtype = np.dtype([("embedding", f"S{blob_size}"), ("label", "i4")])
        result = await async_client.batch_read(keys, _dtype=dtype)

        assert len(result.batch_records) == n
        for i in range(n):
            raw = result.batch_records[i]["embedding"]
            recovered = np.frombuffer(raw, dtype=np.float32)
            np.testing.assert_array_almost_equal(recovered, vectors[i])
            assert result.batch_records[i]["label"] == i


# ── empty batch ──────────────────────────────────────────────────


class TestAsyncEmptyBatch:
    async def test_empty_keys(self, async_client):
        """async batch_read with an empty keys list."""
        dtype = np.dtype([("val", "i4")])
        result = await async_client.batch_read([], _dtype=dtype)

        assert isinstance(result, NumpyBatchRecords)
        assert len(result.batch_records) == 0
        assert len(result.meta) == 0
        assert len(result.result_codes) == 0
