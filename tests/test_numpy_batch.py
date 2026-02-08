"""NumpyBatchRecords 변환 로직 단위 테스트 (서버 불필요)."""

import warnings
from types import SimpleNamespace

import numpy as np
import pytest

from aerospike_py.numpy_batch import NumpyBatchRecords, _batch_records_to_numpy


def _make_batch_record(key, result, record=None):
    """Mock BatchRecord를 SimpleNamespace로 생성."""
    return SimpleNamespace(key=key, result=result, record=record)


def _make_batch_records(records):
    """Mock BatchRecords를 SimpleNamespace로 생성."""
    return SimpleNamespace(batch_records=records)


# ── 정상 변환 테스트 ────────────────────────────────────────────


class TestBasicConversion:
    def test_int64_float64(self):
        dtype = np.dtype([("temperature", "f8"), ("reading_id", "i4")])
        keys = [("test", "demo", "k1"), ("test", "demo", "k2")]
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (
                        None,
                        {"gen": 3, "ttl": 100},
                        {"temperature": 36.5, "reading_id": 1},
                    ),
                ),
                _make_batch_record(
                    ("test", "demo", "k2"),
                    0,
                    (
                        None,
                        {"gen": 1, "ttl": 200},
                        {"temperature": 22.1, "reading_id": 2},
                    ),
                ),
            ]
        )

        result = _batch_records_to_numpy(batch, dtype, keys)

        assert isinstance(result, NumpyBatchRecords)
        assert result.batch_records.dtype == dtype
        assert len(result.batch_records) == 2
        np.testing.assert_almost_equal(result.batch_records[0]["temperature"], 36.5)
        np.testing.assert_almost_equal(result.batch_records[1]["temperature"], 22.1)
        assert result.batch_records[0]["reading_id"] == 1
        assert result.batch_records[1]["reading_id"] == 2

    def test_uint_dtype(self):
        dtype = np.dtype([("count", "u4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"count": 42}),
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.batch_records[0]["count"] == 42


# ── bytes dtype 테스트 ──────────────────────────────────────────


class TestBytesDtype:
    def test_fixed_bytes_S(self):
        dtype = np.dtype([("blob", "S8")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"blob": b"abcdefgh"}),
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.batch_records[0]["blob"] == b"abcdefgh"

    def test_void_bytes_V(self):
        dtype = np.dtype([("raw", "V4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"raw": b"\x01\x02\x03\x04"}),
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert bytes(result.batch_records[0]["raw"]) == b"\x01\x02\x03\x04"


# ── sub-array dtype 테스트 ──────────────────────────────────────


class TestSubArrayDtype:
    def test_embedding_subarray(self):
        dim = 4
        dtype = np.dtype([("embedding", "f4", (dim,)), ("score", "f4")])
        embedding = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (
                        None,
                        {"gen": 1, "ttl": 0},
                        {"embedding": embedding, "score": 0.95},
                    ),
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        np.testing.assert_array_almost_equal(
            result.batch_records[0]["embedding"], [1.0, 2.0, 3.0, 4.0]
        )
        np.testing.assert_almost_equal(result.batch_records[0]["score"], 0.95)


# ── 비허용 dtype 거부 ──────────────────────────────────────────


class TestDtypeValidation:
    def test_unicode_string_rejected(self):
        dtype = np.dtype([("name", "U10")])
        batch = _make_batch_records([])
        with pytest.raises(TypeError, match="kind='U'"):
            _batch_records_to_numpy(batch, dtype, [])

    def test_object_rejected(self):
        dtype = np.dtype([("data", "O")])
        batch = _make_batch_records([])
        with pytest.raises(TypeError, match="kind='O'"):
            _batch_records_to_numpy(batch, dtype, [])


# ── result_code != 0 처리 ──────────────────────────────────────


class TestErrorRecords:
    def test_nonzero_result_code(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 10})
                ),
                _make_batch_record(("test", "demo", "k2"), 2, None),  # RECORD_NOT_FOUND
                _make_batch_record(
                    ("test", "demo", "k3"), 0, (None, {"gen": 2, "ttl": 0}, {"val": 30})
                ),
            ]
        )
        keys = [("test", "demo", f"k{i + 1}") for i in range(3)]
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert result.result_codes[0] == 0
        assert result.result_codes[1] == 2
        assert result.result_codes[2] == 0
        # 실패 레코드는 0으로 채워짐
        assert result.batch_records[1]["val"] == 0
        # 성공 레코드는 정상 값
        assert result.batch_records[0]["val"] == 10
        assert result.batch_records[2]["val"] == 30


# ── missing bin 처리 ────────────────────────────────────────────


class TestMissingBins:
    def test_missing_bin_defaults_to_zero(self):
        dtype = np.dtype([("a", "i4"), ("b", "f8")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"a": 5}),  # b 누락
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.batch_records[0]["a"] == 5
        assert result.batch_records[0]["b"] == 0.0

    def test_none_bins(self):
        dtype = np.dtype([("a", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, None, None),  # meta와 bins 모두 None
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.batch_records[0]["a"] == 0


# ── get() 메서드 ────────────────────────────────────────────────


class TestGetMethod:
    def test_get_by_string_key(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 10})
                ),
                _make_batch_record(
                    ("test", "demo", "k2"), 0, (None, {"gen": 2, "ttl": 0}, {"val": 20})
                ),
            ]
        )
        keys = [("test", "demo", "k1"), ("test", "demo", "k2")]
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert result.get("k1")["val"] == 10
        assert result.get("k2")["val"] == 20

    def test_get_by_int_key(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", 42), 0, (None, {"gen": 1, "ttl": 0}, {"val": 99})
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", 42)])
        assert result.get(42)["val"] == 99

    def test_get_missing_key_raises(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 10})
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        with pytest.raises(KeyError):
            result.get("nonexistent")


# ── meta (gen, ttl) 매핑 ───────────────────────────────────────


class TestMeta:
    def test_meta_gen_ttl(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 5, "ttl": 3600}, {"val": 1}),
                ),
                _make_batch_record(
                    ("test", "demo", "k2"),
                    0,
                    (None, {"gen": 12, "ttl": 7200}, {"val": 2}),
                ),
            ]
        )
        keys = [("test", "demo", "k1"), ("test", "demo", "k2")]
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert result.meta[0]["gen"] == 5
        assert result.meta[0]["ttl"] == 3600
        assert result.meta[1]["gen"] == 12
        assert result.meta[1]["ttl"] == 7200

    def test_meta_defaults_on_error(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(("test", "demo", "k1"), 2, None),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.meta[0]["gen"] == 0
        assert result.meta[0]["ttl"] == 0

    def test_meta_dtype(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 1})
                ),
            ]
        )
        result = _batch_records_to_numpy(batch, dtype, [("test", "demo", "k1")])
        assert result.meta.dtype == np.dtype([("gen", "u4"), ("ttl", "u4")])


# ── empty batch 테스트 ──────────────────────────────────────────


class TestEmptyBatch:
    def test_empty_batch(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records([])
        result = _batch_records_to_numpy(batch, dtype, [])

        assert len(result.batch_records) == 0
        assert len(result.meta) == 0
        assert len(result.result_codes) == 0
        assert result._map == {}


# ── key fallback 경고 테스트 ────────────────────────────────────


class TestKeyFallbackWarning:
    def test_none_key_warns(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(None, 0, (None, {"gen": 1, "ttl": 0}, {"val": 10})),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(batch, dtype, [])
            assert len(w) == 1
            assert "missing or malformed key" in str(w[0].message)
        # fallback to integer index
        assert result.batch_records[0]["val"] == 10
        assert result._map[0] == 0

    def test_short_key_warns(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test",), 0, (None, {"gen": 1, "ttl": 0}, {"val": 20})
                ),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(batch, dtype, [])
            assert len(w) == 1
            assert "missing or malformed key" in str(w[0].message)
        assert result._map[0] == 0

    def test_empty_key_warns(self):
        dtype = np.dtype([("val", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record((), 0, (None, {"gen": 1, "ttl": 0}, {"val": 30})),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(batch, dtype, [])
            assert len(w) == 1
        assert result._map[0] == 0


# ── 대규모 배치 테스트 ────────────────────────────────────────────


class TestLargeBatch:
    def test_1000_records(self):
        n = 1000
        dtype = np.dtype([("id", "i4"), ("value", "f8")])
        records = []
        keys = []
        for i in range(n):
            key = ("test", "demo", f"k{i}")
            keys.append(key)
            records.append(
                _make_batch_record(
                    key,
                    0,
                    (None, {"gen": 1, "ttl": 300}, {"id": i, "value": float(i) * 0.1}),
                )
            )
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert len(result.batch_records) == n
        assert len(result.meta) == n
        assert len(result.result_codes) == n
        # Spot check values
        assert result.batch_records[0]["id"] == 0
        assert result.batch_records[999]["id"] == 999
        np.testing.assert_almost_equal(result.batch_records[500]["value"], 50.0)
        # All result codes should be 0
        assert np.all(result.result_codes == 0)
        # get() should work
        assert result.get("k42")["id"] == 42

    def test_mixed_success_failure_large(self):
        n = 500
        dtype = np.dtype([("val", "i4")])
        records = []
        keys = []
        for i in range(n):
            key = ("test", "demo", f"k{i}")
            keys.append(key)
            if i % 3 == 0:
                # Simulate RECORD_NOT_FOUND
                records.append(_make_batch_record(key, 2, None))
            else:
                records.append(
                    _make_batch_record(key, 0, (None, {"gen": 1, "ttl": 0}, {"val": i}))
                )
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        # Check error records are zero-filled
        for i in range(n):
            if i % 3 == 0:
                assert result.result_codes[i] == 2
                assert result.batch_records[i]["val"] == 0
            else:
                assert result.result_codes[i] == 0
                assert result.batch_records[i]["val"] == i


# ── 컬럼 접근 (vectorized) 테스트 ──────────────────────────────


class TestVectorizedAccess:
    def test_column_slice(self):
        dtype = np.dtype([("x", "f4"), ("y", "f4")])
        records = [
            _make_batch_record(
                ("test", "demo", f"k{i}"),
                0,
                (None, {"gen": 1, "ttl": 0}, {"x": float(i), "y": float(i * 2)}),
            )
            for i in range(10)
        ]
        keys = [("test", "demo", f"k{i}") for i in range(10)]
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        # Column-wise access should work
        x_col = result.batch_records["x"]
        y_col = result.batch_records["y"]
        assert x_col.shape == (10,)
        assert y_col.shape == (10,)
        np.testing.assert_array_almost_equal(x_col, np.arange(10, dtype=np.float32))
        np.testing.assert_array_almost_equal(y_col, np.arange(10, dtype=np.float32) * 2)

    def test_result_code_mask_filtering(self):
        dtype = np.dtype([("val", "i4")])
        records = [
            _make_batch_record(
                ("test", "demo", "k0"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 10})
            ),
            _make_batch_record(("test", "demo", "k1"), 2, None),
            _make_batch_record(
                ("test", "demo", "k2"), 0, (None, {"gen": 1, "ttl": 0}, {"val": 30})
            ),
        ]
        keys = [("test", "demo", f"k{i}") for i in range(3)]
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        # Vectorized mask filtering
        ok_mask = result.result_codes == 0
        ok_records = result.batch_records[ok_mask]
        assert len(ok_records) == 2
        assert ok_records[0]["val"] == 10
        assert ok_records[1]["val"] == 30


# ── strict mode 테스트 ──────────────────────────────────────────


class TestStrictMode:
    def test_strict_warns_missing_bin(self):
        dtype = np.dtype([("a", "i4"), ("b", "f8")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"a": 5}),  # b 누락
                ),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(
                batch, dtype, [("test", "demo", "k1")], strict=True
            )
            missing_warns = [x for x in w if "not found in bins" in str(x.message)]
            assert len(missing_warns) == 1
            assert "'b'" in str(missing_warns[0].message)
        assert result.batch_records[0]["a"] == 5
        assert result.batch_records[0]["b"] == 0.0

    def test_strict_warns_extra_bin(self):
        dtype = np.dtype([("a", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"a": 5, "extra": 99}),
                ),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(
                batch, dtype, [("test", "demo", "k1")], strict=True
            )
            extra_warns = [x for x in w if "not in dtype" in str(x.message)]
            assert len(extra_warns) == 1
            assert "'extra'" in str(extra_warns[0].message)
        assert result.batch_records[0]["a"] == 5

    def test_strict_no_warn_when_match(self):
        dtype = np.dtype([("a", "i4")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"a": 10}),
                ),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _batch_records_to_numpy(
                batch, dtype, [("test", "demo", "k1")], strict=True
            )
            # key 관련 warning 외에는 없어야 함
            schema_warns = [
                x
                for x in w
                if "not found in bins" in str(x.message)
                or "not in dtype" in str(x.message)
            ]
            assert len(schema_warns) == 0
        assert result.batch_records[0]["a"] == 10

    def test_non_strict_no_warns_on_mismatch(self):
        dtype = np.dtype([("a", "i4"), ("b", "f8")])
        batch = _make_batch_records(
            [
                _make_batch_record(
                    ("test", "demo", "k1"),
                    0,
                    (None, {"gen": 1, "ttl": 0}, {"a": 5, "extra": 99}),
                ),
            ]
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _batch_records_to_numpy(
                batch, dtype, [("test", "demo", "k1")], strict=False
            )
            schema_warns = [
                x
                for x in w
                if "not found in bins" in str(x.message)
                or "not in dtype" in str(x.message)
            ]
            assert len(schema_warns) == 0


# ── 대규모 배치 테스트 (10K+) ──────────────────────────────────


class TestVeryLargeBatch:
    def test_10k_records(self):
        n = 10_000
        dtype = np.dtype([("id", "i4"), ("score", "f8"), ("label", "S16")])
        records = []
        keys = []
        for i in range(n):
            key = ("test", "demo", f"k{i}")
            keys.append(key)
            records.append(
                _make_batch_record(
                    key,
                    0,
                    (
                        None,
                        {"gen": 1, "ttl": 600},
                        {"id": i, "score": i * 0.01, "label": f"item{i}".encode()[:16]},
                    ),
                )
            )
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert len(result.batch_records) == n
        assert result.batch_records[0]["id"] == 0
        assert result.batch_records[9999]["id"] == 9999
        np.testing.assert_almost_equal(result.batch_records[5000]["score"], 50.0)
        assert np.all(result.result_codes == 0)
        assert np.all(result.meta["gen"] == 1)
        assert np.all(result.meta["ttl"] == 600)

    def test_50k_records_multi_dtype(self):
        n = 50_000
        dtype = np.dtype(
            [
                ("x", "f4"),
                ("y", "f4"),
                ("z", "f4"),
                ("category", "u1"),
                ("count", "i8"),
            ]
        )
        records = []
        keys = []
        for i in range(n):
            key = ("test", "demo", f"k{i}")
            keys.append(key)
            records.append(
                _make_batch_record(
                    key,
                    0,
                    (
                        None,
                        {"gen": i % 10, "ttl": 1000},
                        {
                            "x": float(i),
                            "y": float(i * 2),
                            "z": float(i * 3),
                            "category": i % 256,
                            "count": i * 100,
                        },
                    ),
                )
            )
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert len(result.batch_records) == n
        # Vectorized column access
        x_col = result.batch_records["x"]
        y_col = result.batch_records["y"]
        assert x_col.shape == (n,)
        assert y_col.shape == (n,)
        # Vectorized mask
        mask = result.batch_records["category"] < 10
        filtered = result.batch_records[mask]
        assert len(filtered) > 0
        # Check memory contiguity
        assert result.batch_records.flags["C_CONTIGUOUS"]

    def test_10k_with_30_percent_errors(self):
        n = 10_000
        dtype = np.dtype([("val", "f8")])
        records = []
        keys = []
        error_count = 0
        for i in range(n):
            key = ("test", "demo", f"k{i}")
            keys.append(key)
            if i % 3 == 0:
                records.append(_make_batch_record(key, 2, None))
                error_count += 1
            else:
                records.append(
                    _make_batch_record(
                        key, 0, (None, {"gen": 1, "ttl": 0}, {"val": float(i)})
                    )
                )
        batch = _make_batch_records(records)
        result = _batch_records_to_numpy(batch, dtype, keys)

        assert np.sum(result.result_codes != 0) == error_count
        ok = result.result_codes == 0
        assert np.sum(ok) == n - error_count
        # Error records should be zero
        error_vals = result.batch_records[~ok]["val"]
        assert np.all(error_vals == 0.0)
