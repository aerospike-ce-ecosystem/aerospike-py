"""Integration tests for numpy batch_read (requires Aerospike server)."""

import numpy as np
import pytest

import aerospike_py
from aerospike_py.numpy_batch import NumpyBatchRecords

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET = "np_batch"


@pytest.fixture(scope="module")
def client():
    try:
        c = aerospike_py.client(CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def cleanup(client):
    keys = []
    yield keys
    for key in keys:
        try:
            client.remove(key)
        except Exception:
            pass


# ── 기본 숫자 타입 변환 ────────────────────────────────────────


class TestNumericBatchRead:
    def test_int_float_batch(self, client, cleanup):
        """int64, float64 bin을 _dtype으로 batch_read."""
        keys = [(NS, SET, f"num_{i}") for i in range(5)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            client.put(key, {"temperature": 20.0 + i * 0.5, "reading_id": i})

        dtype = np.dtype([("temperature", "f8"), ("reading_id", "i4")])
        result = client.batch_read(keys, _dtype=dtype)

        assert isinstance(result, NumpyBatchRecords)
        assert len(result.batch_records) == 5
        assert result.batch_records.dtype == dtype

        for i in range(5):
            np.testing.assert_almost_equal(result.batch_records[i]["temperature"], 20.0 + i * 0.5)
            assert result.batch_records[i]["reading_id"] == i

    def test_result_codes_all_ok(self, client, cleanup):
        """성공한 레코드의 result_codes는 모두 0."""
        keys = [(NS, SET, f"rc_{i}") for i in range(3)]
        for key in keys:
            cleanup.append(key)
            client.put(key, {"val": 1})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read(keys, _dtype=dtype)

        np.testing.assert_array_equal(result.result_codes, [0, 0, 0])

    def test_without_dtype_returns_batch_records(self, client, cleanup):
        """_dtype=None이면 기존 BatchRecords 반환."""
        key = (NS, SET, "nodtype_1")
        cleanup.append(key)
        client.put(key, {"x": 1})

        result = client.batch_read([key])
        assert isinstance(result, aerospike_py.BatchRecords)


# ── meta (gen, ttl) 검증 ──────────────────────────────────────


class TestMetaIntegration:
    def test_gen_increments(self, client, cleanup):
        """put 2회 → gen >= 2 확인."""
        key = (NS, SET, "meta_gen")
        cleanup.append(key)
        client.put(key, {"val": 1})
        client.put(key, {"val": 2})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read([key], _dtype=dtype)

        assert result.meta[0]["gen"] >= 2

    def test_ttl_nonzero(self, client, cleanup):
        """TTL이 설정된 레코드의 ttl > 0 확인."""
        key = (NS, SET, "meta_ttl")
        cleanup.append(key)
        client.put(key, {"val": 1}, meta={"ttl": 600})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read([key], _dtype=dtype)

        assert result.meta[0]["ttl"] > 0


# ── key 기반 조회 (get 메서드) ──────────────────────────────────


class TestGetMethod:
    def test_get_by_key(self, client, cleanup):
        """get()으로 primary_key 기반 조회."""
        keys = [(NS, SET, f"get_{i}") for i in range(3)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            client.put(key, {"val": (i + 1) * 10})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read(keys, _dtype=dtype)

        assert result.get("get_0")["val"] == 10
        assert result.get("get_1")["val"] == 20
        assert result.get("get_2")["val"] == 30

    def test_get_int_key(self, client, cleanup):
        """정수 primary_key로 get() 조회."""
        key = (NS, SET, 42)
        cleanup.append(key)
        client.put(key, {"val": 99})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read([key], _dtype=dtype)

        assert result.get(42)["val"] == 99


# ── missing 레코드 처리 ─────────────────────────────────────────


class TestMissingRecords:
    def test_nonexistent_key_zeroed(self, client, cleanup):
        """존재하지 않는 key → 0/빈값, result_code != 0."""
        existing = (NS, SET, "exist_1")
        missing = (NS, SET, "nonexistent_xyz")
        cleanup.append(existing)
        client.put(existing, {"val": 42})

        dtype = np.dtype([("val", "i4")])
        result = client.batch_read([existing, missing], _dtype=dtype)

        assert result.result_codes[0] == 0
        assert result.result_codes[1] != 0
        assert result.batch_records[0]["val"] == 42
        assert result.batch_records[1]["val"] == 0

    def test_missing_bin_zeroed(self, client, cleanup):
        """레코드에 없는 bin → 0으로 채워짐."""
        key = (NS, SET, "missing_bin_1")
        cleanup.append(key)
        client.put(key, {"a": 5})

        dtype = np.dtype([("a", "i4"), ("b", "f8")])
        result = client.batch_read([key], _dtype=dtype)

        assert result.batch_records[0]["a"] == 5
        assert result.batch_records[0]["b"] == 0.0


# ── bins 필터링 ─────────────────────────────────────────────────


class TestBinsFilter:
    def test_select_specific_bins(self, client, cleanup):
        """bins 파라미터로 특정 bin만 읽기."""
        key = (NS, SET, "bins_filter_1")
        cleanup.append(key)
        client.put(key, {"a": 1, "b": 2, "c": 3})

        dtype = np.dtype([("a", "i4"), ("b", "i4")])
        result = client.batch_read([key], bins=["a", "b"], _dtype=dtype)

        assert result.batch_records[0]["a"] == 1
        assert result.batch_records[0]["b"] == 2


# ── bytes blob 저장/조회 ────────────────────────────────────────


class TestBytesBlob:
    def test_bytes_blob_roundtrip(self, client, cleanup):
        """bytes blob 저장 후 batch_read로 조회."""
        key = (NS, SET, "blob_1")
        cleanup.append(key)
        raw = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        client.put(key, {"data": raw, "score": 0.5})

        dtype = np.dtype([("data", "S8"), ("score", "f4")])
        result = client.batch_read([key], _dtype=dtype)

        assert result.batch_records[0]["data"] == raw
        np.testing.assert_almost_equal(result.batch_records[0]["score"], 0.5, decimal=5)


# ── vector embedding 사용 사례 ──────────────────────────────────


class TestVectorEmbedding:
    def test_vector_as_bytes_blob(self, client, cleanup):
        """float32 벡터를 bytes로 저장 후 batch_read → frombuffer 변환."""
        dim = 8
        vec = np.random.rand(dim).astype(np.float32)
        blob = vec.tobytes()

        key = (NS, SET, "vec_blob_1")
        cleanup.append(key)
        client.put(key, {"embedding": blob, "score": 0.95})

        blob_size = dim * 4
        dtype = np.dtype([("embedding", f"S{blob_size}"), ("score", "f4")])
        result = client.batch_read([key], _dtype=dtype)

        recovered = np.frombuffer(result.batch_records[0]["embedding"], dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, vec)

    def test_multiple_vectors_batch(self, client, cleanup):
        """여러 벡터를 batch_read로 한 번에 조회."""
        dim = 4
        n = 10
        vectors = [np.random.rand(dim).astype(np.float32) for _ in range(n)]

        keys = [(NS, SET, f"mvec_{i}") for i in range(n)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            client.put(key, {"embedding": vectors[i].tobytes(), "label": i})

        blob_size = dim * 4
        dtype = np.dtype([("embedding", f"S{blob_size}"), ("label", "i4")])
        result = client.batch_read(keys, _dtype=dtype)

        assert len(result.batch_records) == n
        for i in range(n):
            raw = result.batch_records[i]["embedding"]
            recovered = np.frombuffer(raw, dtype=np.float32)
            np.testing.assert_array_almost_equal(recovered, vectors[i])
            assert result.batch_records[i]["label"] == i


# ── columnar 접근 패턴 ──────────────────────────────────────────


class TestColumnarAccess:
    def test_vectorized_mean(self, client, cleanup):
        """columnar 접근으로 numpy vectorized 연산."""
        n = 20
        keys = [(NS, SET, f"col_{i}") for i in range(n)]
        for i, key in enumerate(keys):
            cleanup.append(key)
            client.put(key, {"temperature": float(i), "humidity": float(i * 2)})

        dtype = np.dtype([("temperature", "f8"), ("humidity", "f8")])
        result = client.batch_read(keys, _dtype=dtype)

        ok = result.result_codes == 0
        temps = result.batch_records["temperature"][ok]
        assert len(temps) == n
        np.testing.assert_almost_equal(np.mean(temps), (n - 1) / 2.0)

    def test_filtering_by_result_code(self, client, cleanup):
        """result_codes로 성공 레코드만 필터링."""
        existing = [(NS, SET, f"filt_{i}") for i in range(3)]
        missing = [(NS, SET, "filt_missing")]
        for i, key in enumerate(existing):
            cleanup.append(key)
            client.put(key, {"val": (i + 1) * 10})

        all_keys = existing + missing
        dtype = np.dtype([("val", "i4")])
        result = client.batch_read(all_keys, _dtype=dtype)

        ok_mask = result.result_codes == 0
        assert ok_mask.sum() == 3
        vals = result.batch_records["val"][ok_mask]
        np.testing.assert_array_equal(sorted(vals), [10, 20, 30])


# ── empty batch ──────────────────────────────────────────────────


class TestEmptyBatch:
    def test_empty_keys(self, client):
        """빈 keys 리스트로 batch_read."""
        dtype = np.dtype([("val", "i4")])
        result = client.batch_read([], _dtype=dtype)

        assert isinstance(result, NumpyBatchRecords)
        assert len(result.batch_records) == 0
        assert len(result.meta) == 0
        assert len(result.result_codes) == 0
