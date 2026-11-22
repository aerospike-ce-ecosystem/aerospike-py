"""The pure-Python NumPy conversion follows the native conversion's rules (no server).

``aerospike_py.numpy_batch._batch_records_to_numpy`` builds a
``NumpyBatchRecords`` by assigning through NumPy instead of copying raw bytes.
It must accept and reject the same inputs as ``LazyBatchRecords.to_numpy``:

- a numeric sub-array field is a vector: it takes a blob of exactly
  ``itemsize`` bytes, a scalar only when it has one element, or a sequence of
  exactly its shape;
- a finite value too large for an ``f2``/``f4`` field raises ``OverflowError``
  instead of turning into ±inf; NaN and infinities are kept;
- the dtype goes through the same native validator, with one deliberate
  difference: a byte-swapped field is accepted here, because NumPy swaps the
  bytes on assignment;
- row ``i`` is request ``i`` and only real user keys are indexed.

The fake batch records copy the helpers of ``tests/unit/test_numpy_conversion.py``.
"""

import math
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from aerospike_py._aerospike import validate_numpy_dtype
from aerospike_py.numpy_batch import NumpyBatchRecords, _batch_records_to_numpy

NON_NATIVE = ">" if sys.byteorder == "little" else "<"


@dataclass
class FakeBatchRecord:
    key: Any
    result: int
    record: Any  # tuple or None


@dataclass
class FakeBatchRecords:
    batch_records: list[FakeBatchRecord]


def _make_batch_record(key, result, record=None):
    return FakeBatchRecord(key=key, result=result, record=record)


def _make_batch_records(records):
    return FakeBatchRecords(batch_records=records)


def _convert_one(dtype, bins):
    """Convert a single successful row carrying ``bins``."""
    batch = _make_batch_records([_make_batch_record(("test", "demo", "k1"), 0, (None, {"gen": 1, "ttl": 0}, bins))])
    return _batch_records_to_numpy(batch, np.dtype(dtype), [("test", "demo", "k1")])


# ── vectors ─────────────────────────────────────────────────────


class TestVectorFields:
    @pytest.mark.parametrize(
        ("field", "values"),
        [
            pytest.param(("v", "f4", (1,)), [1.5], id="f4_1"),
            pytest.param(("v", "f8", (4,)), [1.0, -2.5, 3.25, 4e300], id="f8_4"),
            pytest.param(("v", "i4", (2, 3)), [[1, -2, 3], [4, 5, -6]], id="i4_2x3"),
            pytest.param(("v", "u2", (3,)), [0, 1, 65535], id="u2_3"),
        ],
    )
    def test_blob_of_exactly_itemsize_bytes_loads(self, field, values):
        """The blob is native-endian bytes, as the native writer stores it."""
        _, base, shape = field
        blob = np.array(values, dtype=np.dtype(base).newbyteorder("=")).tobytes()
        assert len(blob) == np.dtype([field]).itemsize

        result = _convert_one([field], {"v": blob})

        assert result.batch_records[0]["v"].shape == shape
        assert result.batch_records[0]["v"].tolist() == values

    @pytest.mark.parametrize(
        ("field", "length", "expected"),
        [
            pytest.param(("v", "f8", (4,)), 8, 32, id="short"),
            pytest.param(("v", "f8", (4,)), 40, 32, id="long"),
            pytest.param(("v", "f4", (1,)), 3, 4, id="short_1"),
            pytest.param(("v", "i4", (2, 3)), 0, 24, id="empty"),
        ],
    )
    def test_blob_of_another_length_raises(self, field, length, expected):
        with pytest.raises(ValueError, match="vector length mismatch for field 'v'") as excinfo:
            _convert_one([field], {"v": b"\x00" * length})
        assert f"the stored blob has {length} bytes, the dtype expects {expected}" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("field", "scalar", "expected"),
        [
            pytest.param(("v", "f4", (1,)), 7.25, [7.25], id="float"),
            pytest.param(("v", "i8", (1,)), -7, [-7], id="int"),
            pytest.param(("v", "f8", (1,)), 7, [7.0], id="int_into_float"),
            pytest.param(("v", "i1", (1,)), True, [1], id="bool"),
        ],
    )
    def test_scalar_loads_into_a_one_element_vector(self, field, scalar, expected):
        """Releases up to 0.14.x stored ``(1,)`` fields as scalars."""
        result = _convert_one([field], {"v": scalar})

        assert result.batch_records[0]["v"].tolist() == expected

    @pytest.mark.parametrize(
        ("field", "count"),
        [
            pytest.param(("v", "f8", (4,)), 4, id="f8_4"),
            pytest.param(("v", "i4", (2, 3)), 6, id="i4_2x3"),
        ],
    )
    def test_scalar_for_a_longer_vector_raises(self, field, count):
        with pytest.raises(ValueError, match="vector length mismatch for field 'v'") as excinfo:
            _convert_one([field], {"v": 1.5})
        assert f"the stored value is a scalar, the dtype expects {count} elements" in str(excinfo.value)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param([1.0, 2.0, 3.0, 4.0], id="list"),
            pytest.param((1.0, 2.0, 3.0, 4.0), id="tuple"),
            pytest.param(np.array([1.0, 2.0, 3.0, 4.0], dtype="f4"), id="ndarray"),
        ],
    )
    def test_sequence_of_the_right_shape_loads(self, value):
        result = _convert_one([("v", "f8", (4,))], {"v": value})

        assert result.batch_records[0]["v"].tolist() == [1.0, 2.0, 3.0, 4.0]

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param([1.0, 2.0, 3.0], id="too_short"),
            pytest.param([1.0, 2.0, 3.0, 4.0, 5.0], id="too_long"),
            pytest.param([1.0], id="single_element_list"),
            pytest.param(np.zeros((2, 2)), id="same_size_other_shape"),
            pytest.param(np.array(1.0), id="zero_dim_array"),
        ],
    )
    def test_sequence_of_another_shape_raises(self, value):
        """NumPy would broadcast a length-1 sequence into every slot; the conversion refuses instead."""
        with pytest.raises(ValueError, match="vector length mismatch for field 'v'") as excinfo:
            _convert_one([("v", "f8", (4,))], {"v": value})
        assert "the dtype expects (4,)" in str(excinfo.value)

    def test_unsupported_value_type_raises_type_error(self):
        """A string has no defined placement in a numeric vector; the native path raises ``TypeError`` too."""
        with pytest.raises(TypeError, match="unsupported value type str for numpy vector field 'v'"):
            _convert_one([("v", "f8", (4,))], {"v": "1,2,3,4"})


# ── floats ──────────────────────────────────────────────────────

F16_MAX = float(np.finfo(np.float16).max)
F32_MAX = float(np.finfo(np.float32).max)


class TestFloatRange:
    @pytest.mark.parametrize(
        ("value", "field", "width"),
        [
            pytest.param(70000.0, ("v", "f2"), "f16", id="f2"),
            pytest.param(-70000.0, ("v", "f2"), "f16", id="f2_negative"),
            pytest.param(65505.0, ("v", "f2"), "f16", id="f2_just_above_max"),
            pytest.param(70000, ("v", "f2"), "f16", id="f2_from_int"),
            pytest.param(70000.0, ("v", "f2", (1,)), "f16", id="f2_scalar_vector"),
            pytest.param(1e39, ("v", "f4"), "f32", id="f4"),
            pytest.param(-1e39, ("v", "f4"), "f32", id="f4_negative"),
            pytest.param(3.5e38, ("v", "f4"), "f32", id="f4_just_above_max"),
            pytest.param(2**200, ("v", "f4"), "f32", id="f4_from_int"),
        ],
    )
    def test_finite_overflow_raises(self, value, field, width):
        with pytest.raises(OverflowError, match=f"does not fit in {width} for field 'v'"):
            _convert_one([field], {"v": value})

    @pytest.mark.parametrize(
        ("value", "field"),
        [
            pytest.param([70000.0, 1.0, 2.0, 3.0], ("v", "f2", (4,)), id="f2_list"),
            pytest.param(np.array([1.0, -70000.0]), ("v", "f2", (2,)), id="f2_ndarray"),
            pytest.param((1e39, 1.0), ("v", "f4", (2,)), id="f4_tuple"),
        ],
    )
    def test_finite_overflow_inside_a_vector_sequence_raises(self, value, field):
        """A list, tuple or ndarray for a vector field obeys the same range rule as a scalar.

        Left to NumPy, the cast turns the out-of-range element into ±inf and
        only emits a ``RuntimeWarning``.
        """
        with pytest.raises(OverflowError, match="field 'v'"):
            _convert_one([field], {"v": value})

    @pytest.mark.parametrize(
        ("value", "kind"),
        [
            pytest.param(F16_MAX, "f2", id="f2_max"),
            pytest.param(-F16_MAX, "f2", id="f2_min"),
            pytest.param(F32_MAX, "f4", id="f4_max"),
            pytest.param(-F32_MAX, "f4", id="f4_min"),
            pytest.param(1e300, "f8", id="f8_large"),
        ],
    )
    def test_largest_finite_value_still_fits(self, value, kind):
        result = _convert_one([("v", kind)], {"v": value})

        assert float(result.batch_records[0]["v"]) == value

    @pytest.mark.parametrize("kind", ["f2", "f4", "f8"])
    def test_nan_and_infinities_are_preserved(self, kind):
        result = _convert_one(
            [("nan", kind), ("inf", kind), ("ninf", kind)],
            {"nan": math.nan, "inf": math.inf, "ninf": -math.inf},
        )

        row = result.batch_records[0]
        assert math.isnan(row["nan"])
        assert row["inf"] == math.inf
        assert row["ninf"] == -math.inf


# ── fixed-width bytes ───────────────────────────────────────────


class TestFixedWidthBytes:
    def test_shorter_values_are_padded_and_longer_ones_truncated(self):
        """Same rule as the native read: null-pad to ``N`` bytes, keep the first ``N``."""
        result = _convert_one(
            [("short", "S8"), ("exact", "S4"), ("long", "S4")],
            {"short": b"abc", "exact": b"abcd", "long": b"abcdefghij"},
        )

        rows = result.batch_records
        assert rows[0].tolist() == (b"abc", b"abcd", b"abcd")
        assert rows["short"].tobytes() == b"abc\x00\x00\x00\x00\x00"

    def test_a_string_is_stored_as_its_utf8_bytes(self):
        """Same rule as the native read; NumPy alone would only take ASCII."""
        result = _convert_one([("s", "S8")], {"s": "é1"})

        assert result.batch_records[0]["s"] == "é1".encode()

    def test_a_failed_assignment_keeps_its_kind_and_names_the_row(self):
        """The row context is added whatever the failing exception's constructor takes."""
        with pytest.raises(ValueError, match=r"field 'n'.*index 0.*key='k1'"):
            _convert_one([("n", "i4")], {"n": "not a number"})


# ── dtype validation ────────────────────────────────────────────

# (dtype, message fragment); every one is rejected with TypeError.
REJECTED_DTYPES = [
    pytest.param(np.dtype([("v", "O")]), "kind='O'", id="object_field"),
    pytest.param(np.dtype([("s", [("x", "i4"), ("o", "O")])]), "holds Python objects", id="object_nested_in_struct"),
    pytest.param(np.dtype("f8"), "must be a structured dtype with named fields", id="unstructured"),
    pytest.param(np.dtypes.StringDType(), "variable-length StringDType is not supported", id="string_dtype"),
    pytest.param(np.dtype([("v", "U4")]), "kind='U'", id="unicode_field"),
]

VALID_DTYPES = [
    pytest.param(np.dtype([("i", "i1"), ("u", "u8"), ("f", "f2"), ("d", "f8")]), id="numeric"),
    pytest.param(np.dtype([("s", "S8"), ("raw", "V4")]), id="bytes"),
    pytest.param(np.dtype([("vec", "f4", (4,)), ("one", "i8", (1,)), ("mat", "u2", (2, 3))]), id="sub_arrays"),
    pytest.param(np.dtype([("nested", [("a", "i4"), ("b", "f8")])]), id="nested_struct"),
    pytest.param(np.dtype([("v", "<i4")] if sys.byteorder == "little" else [("v", ">i4")]), id="explicit_native"),
]


class TestDtypeValidation:
    @pytest.mark.parametrize(("dtype", "message"), REJECTED_DTYPES)
    def test_rejected_dtypes(self, dtype, message):
        batch = _make_batch_records([])

        with pytest.raises(TypeError, match=message):
            _batch_records_to_numpy(batch, dtype, [])

    @pytest.mark.parametrize(
        ("dtype", "bins", "expected"),
        [
            pytest.param([("v", f"{NON_NATIVE}i4")], {"v": 0x01020304}, 0x01020304, id="int"),
            pytest.param([("v", f"{NON_NATIVE}i4")], {"v": 1}, 1, id="int_one"),
            pytest.param([("v", f"{NON_NATIVE}f8")], {"v": -2.5}, -2.5, id="float"),
        ],
    )
    def test_non_native_byte_order_is_accepted_and_round_trips(self, dtype, bins, expected):
        """Accepted on purpose: NumPy swaps the bytes on assignment, so the value is right.

        The native paths reject the same dtype, because they copy raw bytes.
        """
        result = _convert_one(dtype, bins)

        assert result.batch_records.dtype == np.dtype(dtype)
        assert result.batch_records[0]["v"] == expected

    def test_non_native_vector_loads_a_native_blob(self):
        """A vector blob holds native-endian bytes; NumPy converts them to the field's byte order."""
        blob = np.array([1.0, 2.0, 3.0, 4.0], dtype="=f4").tobytes()

        result = _convert_one([("v", f"{NON_NATIVE}f4", (4,))], {"v": blob})

        assert result.batch_records[0]["v"].tolist() == [1.0, 2.0, 3.0, 4.0]


class TestValidateNumpyDtype:
    @pytest.mark.parametrize("dtype", VALID_DTYPES)
    @pytest.mark.parametrize("require_native", [True, False])
    def test_accepts_valid_dtypes(self, dtype, require_native):
        assert validate_numpy_dtype(dtype, require_native_byteorder=require_native) is None

    @pytest.mark.parametrize(
        "dtype",
        [
            pytest.param(np.dtype([("v", f"{NON_NATIVE}i4")]), id="field"),
            pytest.param(np.dtype([("v", f"{NON_NATIVE}f4", (4,))]), id="sub_array_base"),
        ],
    )
    def test_rejects_non_native_byte_order_by_default(self, dtype):
        with pytest.raises(ValueError, match="dtype field 'v' has non-native byte order"):
            validate_numpy_dtype(dtype)

    def test_accepts_non_native_byte_order_when_not_required(self):
        assert validate_numpy_dtype(np.dtype([("v", f"{NON_NATIVE}i4")]), require_native_byteorder=False) is None

    @pytest.mark.parametrize(("dtype", "message"), REJECTED_DTYPES)
    @pytest.mark.parametrize("require_native", [True, False])
    def test_other_rules_apply_whatever_the_byte_order_flag(self, dtype, message, require_native):
        with pytest.raises(TypeError, match=message):
            validate_numpy_dtype(dtype, require_native_byteorder=require_native)

    def test_require_native_byteorder_is_keyword_only(self):
        with pytest.raises(TypeError):
            validate_numpy_dtype(np.dtype([("v", "i4")]), False)  # type: ignore[misc]


# ── keys and rows ───────────────────────────────────────────────


class TestKeysAndRows:
    """The same scenario the integration test runs through the native path."""

    def test_row_i_is_request_i_and_only_user_keys_are_indexed(self):
        digest = b"\x01" * 20
        batch = _make_batch_records(
            [
                _make_batch_record(("test", "demo", None, digest), 0, (None, {"gen": 1, "ttl": 0}, {"v": 1611})),
                _make_batch_record(("test", "demo", 1, b"\x02" * 20), 0, (None, {"gen": 1, "ttl": 0}, {"v": 1001})),
                _make_batch_record(("test", "demo", 0, b"\x03" * 20), 0, (None, {"gen": 1, "ttl": 0}, {"v": 1000})),
                _make_batch_record(("test", "demo", None, b"\x04" * 20), 2, None),
                _make_batch_record(("test", "demo", 1, b"\x02" * 20), 0, (None, {"gen": 2, "ttl": 0}, {"v": 2001})),
            ]
        )

        result = _batch_records_to_numpy(batch, np.dtype([("v", "i8")]), [])

        assert isinstance(result, NumpyBatchRecords)
        assert result.result_codes.tolist() == [0, 0, 0, 2, 0]
        assert result.batch_records["v"].tolist() == [1611, 1001, 1000, 0, 2001]
        assert result.meta["gen"].tolist() == [1, 1, 1, 0, 2]
        # Real integer keys point at their own rows, the repeated key at its last row.
        assert result.get(0)["v"] == 1000
        assert result.get(1)["v"] == 2001
        for absent in (3, None, digest, "__no_user_key_0__", "__no_user_key_3__"):
            assert absent not in result
            with pytest.raises(KeyError):
                result.get(absent)
        assert result._map == {1: 4, 0: 2}


def test_nested_numeric_subdtype_shape_and_blob_length():
    dtype = np.dtype([("v", np.dtype((np.dtype(("f4", (2,))), (2,))))])
    payload = np.arange(4, dtype="f4").tobytes()
    with pytest.raises(ValueError, match="vector length mismatch"):
        _convert_one(dtype, {"v": payload[:8]})
    np.testing.assert_array_equal(_convert_one(dtype, {"v": payload}).batch_records["v"][0], [[0, 1], [2, 3]])
