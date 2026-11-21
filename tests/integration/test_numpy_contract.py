"""NumPy batch read/write contract, pinned for the sync and the async client.

Input API
    ``batch_write_numpy(data, ns, set)`` takes the layout from ``data.dtype``.
    ``_dtype`` is optional; when it is given and differs from ``data.dtype`` the
    call raises ``ValueError`` before the first row is sent.
Layout
    Any 1-D view is written row by row, in view order. A dtype the native
    buffer code cannot handle is rejected with a clear error, in both
    directions, before anything is written.
Vectors and numerics
    A numeric sub-array field is a vector stored as one blob of exactly
    ``itemsize`` bytes, including the one-element ``(1,)`` shape that releases
    up to 0.14.x stored as a scalar. Such a legacy scalar still reads into a
    ``(1,)`` field; any other length mismatch is an error. ``S<N>`` fields keep
    their padding and truncation rules. A finite value too large for an
    ``f2``/``f4`` field raises ``OverflowError``; NaN and infinities are kept.
Keys and rows
    Output row ``i`` is request ``i``, hit or miss. Only real user keys are
    indexed: a digest-only row is reachable by position only, and a repeated
    user key points at its last row. The key field of a write is one value: a
    sub-array or a nested structure is refused.
What is trusted
    The layout the rows are copied through is NumPy's own: of the real
    ``numpy.dtype`` on the way out, of the base ``numpy.ndarray`` on the way
    in. An object that only describes itself as one cannot move a read or a
    write outside the buffer.
"""

import asyncio
import math
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from aerospike_py import exp
from aerospike_py import hll_operations as hll
from tests import AEROSPIKE_CONFIG
from tests.helpers import invoke

NS = "test"
SET = "numpy_contract"
SET_B = "numpy_contract_b"

NON_NATIVE = ">" if sys.byteorder == "little" else "<"

ROW_DTYPE = np.dtype([("_key", "i8"), ("score", "f8"), ("count", "i4")])
READ_DTYPE = np.dtype([("score", "f8"), ("count", "i4")])


def _rows(user_keys):
    """One row per user key: ``score = key / 2``, ``count = key * 10``."""
    return np.array([(k, k / 2, k * 10) for k in user_keys], dtype=ROW_DTYPE)


def _keys(user_keys, set_name=SET):
    return [(NS, set_name, int(k)) for k in user_keys]


async def _read(client, keys, dtype):
    handle = await invoke(client, "batch_read", keys)
    return handle.to_numpy(dtype)


async def _result_codes(client, keys):
    handle = await invoke(client, "batch_read", keys)
    return [br.result for br in handle.batch_records]


async def _put(client, cleanup, key, bins):
    cleanup.append(key)
    await invoke(client, "put", key, bins)


# ── input API ───────────────────────────────────────────────────


class TestInputApi:
    @pytest.mark.parametrize("how", ["omitted", "positional", "keyword"])
    async def test_layout_comes_from_data_dtype(self, any_client, any_cleanup, how):
        """The dtype argument is optional; given, it may be any dtype equal to ``data.dtype``."""
        user_keys = [101, 102, 103]
        keys = _keys(user_keys)
        any_cleanup.extend(keys)
        # Equal to ROW_DTYPE but a separate object: equality is what counts.
        declared = np.dtype([("_key", "i8"), ("score", "f8"), ("count", "i4")])
        args, kwargs = {
            "omitted": ((), {}),
            "positional": ((declared,), {}),
            "keyword": ((), {"_dtype": declared}),
        }[how]

        result = await invoke(any_client, "batch_write_numpy", _rows(user_keys), NS, SET, *args, **kwargs)

        assert [br.result for br in result.batch_records] == [0, 0, 0]
        assert [br.key.user_key for br in result.batch_records] == user_keys
        read = await _read(any_client, keys, READ_DTYPE)
        np.testing.assert_array_equal(read.batch_records["score"], [50.5, 51.0, 51.5])
        np.testing.assert_array_equal(read.batch_records["count"], [1010, 1020, 1030])

    @pytest.mark.parametrize("as_keyword", [False, True], ids=["positional", "keyword"])
    @pytest.mark.parametrize(
        "declared",
        [
            np.dtype([("_key", "i8"), ("score", "f4"), ("count", "i4")]),
            np.dtype([("_key", "i8"), ("points", "f8"), ("count", "i4")]),
            np.dtype([("_key", "i8"), ("count", "i4"), ("score", "f8")]),
            np.dtype({"names": ["_key", "score", "count"], "formats": ["i8", "f8", "i4"], "itemsize": 24}),
        ],
        ids=["other_field_type", "other_field_name", "other_field_order", "other_itemsize"],
    )
    async def test_mismatched_dtype_raises_before_anything_is_written(
        self, any_client, any_cleanup, declared, as_keyword
    ):
        """Reading the buffer through another dtype would reinterpret its bytes, so the call fails."""
        user_keys = [111, 112, 113]
        keys = _keys(user_keys)
        any_cleanup.extend(keys)
        args, kwargs = ((), {"_dtype": declared}) if as_keyword else ((declared,), {})

        with pytest.raises(ValueError, match="_dtype does not match the array"):
            await invoke(any_client, "batch_write_numpy", _rows(user_keys), NS, SET, *args, **kwargs)

        assert await _result_codes(any_client, keys) == [2, 2, 2]


# ── layout ──────────────────────────────────────────────────────

BASE_KEYS = [201, 202, 203, 204, 205, 206]


class TestLayouts:
    @pytest.mark.parametrize(
        ("view", "written"),
        [
            pytest.param(lambda a: a, BASE_KEYS, id="contiguous"),
            pytest.param(lambda a: a[::2], [201, 203, 205], id="step_slice"),
            pytest.param(lambda a: a[::-1], BASE_KEYS[::-1], id="reversed"),
            pytest.param(lambda a: a[::-2], [206, 204, 202], id="reversed_step"),
            pytest.param(lambda a: a[2:4], [203, 204], id="offset_slice"),
            pytest.param(lambda a: a[:0], [], id="empty"),
        ],
    )
    async def test_view_writes_exactly_its_rows_in_view_order(self, any_client, any_cleanup, view, written):
        all_keys = _keys(BASE_KEYS)
        any_cleanup.extend(all_keys)
        data = view(_rows(BASE_KEYS))

        result = await invoke(any_client, "batch_write_numpy", data, NS, SET)

        assert [br.key.user_key for br in result.batch_records] == written
        assert [br.result for br in result.batch_records] == [0] * len(written)
        # Rows outside the view were not written; rows inside carry their own values.
        codes = await _result_codes(any_client, all_keys)
        assert codes == [0 if k in written else 2 for k in BASE_KEYS]
        read = await _read(any_client, _keys(BASE_KEYS), READ_DTYPE)
        expected_scores = [k / 2 if k in written else 0.0 for k in BASE_KEYS]
        np.testing.assert_array_equal(read.batch_records["score"], expected_scores)

    async def test_field_subset_view_writes_only_its_fields(self, any_client, any_cleanup):
        """``arr[["_key", "count"]]`` is a view with gaps in its layout; only its fields become bins."""
        keys = _keys([211, 212])
        any_cleanup.extend(keys)
        data = _rows([211, 212])[["_key", "count"]]
        assert data.dtype.itemsize == ROW_DTYPE.itemsize  # still the padded parent layout

        result = await invoke(any_client, "batch_write_numpy", data, NS, SET)

        assert [br.result for br in result.batch_records] == [0, 0]
        assert (await invoke(any_client, "get", keys[0])).bins == {"count": 2110}
        assert (await invoke(any_client, "get", keys[1])).bins == {"count": 2120}

    async def test_async_write_copies_the_rows_before_it_yields(self, async_client, async_cleanup):
        """The async writer owns its rows; the array's buffer is not read after the call yields.

        The task is started and allowed to yield once, then the array is
        overwritten. The stored values must be the ones the array held when
        the call was made.
        """
        user_keys = list(range(221, 261))
        keys = _keys(user_keys)
        async_cleanup.extend(keys)
        data = _rows(user_keys)

        task = asyncio.ensure_future(async_client.batch_write_numpy(data, NS, SET))
        await asyncio.sleep(0)
        data["score"] = -1.0
        data["count"] = -1
        result = await task

        assert [br.result for br in result.batch_records] == [0] * len(user_keys)
        read = await _read(async_client, keys, READ_DTYPE)
        np.testing.assert_array_equal(read.batch_records["score"], [k / 2 for k in user_keys])
        np.testing.assert_array_equal(read.batch_records["count"], [k * 10 for k in user_keys])


def _keyed(dtype, user_keys):
    data = np.zeros(len(user_keys), dtype=dtype)
    data["_key"] = user_keys
    return data


def _two_d():
    data = np.zeros((2, 2), dtype=ROW_DTYPE)
    data["_key"] = [[301, 302], [303, 304]]
    return data


# (array factory, user keys it would write, exception type, message fragment)
REJECTED_ARRAYS = [
    pytest.param(_two_d, [301, 302, 303, 304], ValueError, "must be 1-dimensional", id="two_dimensional"),
    pytest.param(
        lambda: np.arange(301, 305, dtype="i8"),
        [301, 302, 303, 304],
        TypeError,
        "must be a structured dtype with named fields",
        id="unstructured",
    ),
    pytest.param(
        lambda: np.array(["301", "302"], dtype=np.dtypes.StringDType()),
        [301, 302],
        TypeError,
        "variable-length StringDType is not supported",
        id="string_dtype",
    ),
    pytest.param(
        lambda: _keyed([("_key", "i8"), ("o", "O")], [301, 302]),
        [301, 302],
        TypeError,
        "kind='O'",
        id="object_field",
    ),
    pytest.param(
        lambda: _keyed([("_key", "i8"), ("s", [("x", "i4"), ("o", "O")])], [301, 302]),
        [301, 302],
        TypeError,
        "holds Python objects",
        id="object_nested_in_struct",
    ),
    pytest.param(
        lambda: _keyed([("_key", "i8"), ("v", f"{NON_NATIVE}f8")], [301, 302]),
        [301, 302],
        ValueError,
        "non-native byte order",
        id="non_native_field",
    ),
    pytest.param(
        lambda: _keyed([("_key", f"{NON_NATIVE}i8"), ("v", "f8")], [301, 302]),
        [301, 302],
        ValueError,
        "non-native byte order",
        id="non_native_key",
    ),
    pytest.param(
        lambda: _keyed([("_key", "i8"), ("emb", f"{NON_NATIVE}f4", (4,))], [301, 302]),
        [301, 302],
        ValueError,
        "non-native byte order",
        id="non_native_subarray",
    ),
]

# (read dtype, exception type, message fragment)
REJECTED_READ_DTYPES = [
    pytest.param(np.dtype("f8"), TypeError, "must be a structured dtype with named fields", id="unstructured"),
    pytest.param(np.dtypes.StringDType(), TypeError, "variable-length StringDType is not supported", id="string_dtype"),
    pytest.param(np.dtype([("v", "O")]), TypeError, "kind='O'", id="object_field"),
    pytest.param(np.dtype([("s", [("v", "i4"), ("o", "O")])]), TypeError, "holds Python objects", id="nested_object"),
    pytest.param(np.dtype([("v", f"{NON_NATIVE}i4")]), ValueError, "non-native byte order", id="non_native_field"),
    pytest.param(
        np.dtype([("v", f"{NON_NATIVE}f4", (4,))]), ValueError, "non-native byte order", id="non_native_subarray"
    ),
    pytest.param(np.dtype([("v", "U4")]), TypeError, "kind='U'", id="unicode_field"),
]


class TestRejectedLayouts:
    @pytest.mark.parametrize(("make", "user_keys", "exc", "message"), REJECTED_ARRAYS)
    async def test_batch_write_numpy_rejects_before_writing(
        self, any_client, any_cleanup, make, user_keys, exc, message
    ):
        keys = _keys(user_keys)
        any_cleanup.extend(keys)

        with pytest.raises(exc, match=message):
            await invoke(any_client, "batch_write_numpy", make(), NS, SET)

        assert await _result_codes(any_client, keys) == [2] * len(keys)

    @pytest.mark.parametrize(("dtype", "exc", "message"), REJECTED_READ_DTYPES)
    async def test_to_numpy_rejects(self, any_client, any_cleanup, dtype, exc, message):
        key = (NS, SET, 321)
        await _put(any_client, any_cleanup, key, {"v": 1})
        handle = await invoke(any_client, "batch_read", [key])

        with pytest.raises(exc, match=message):
            handle.to_numpy(dtype)


# ── vectors ─────────────────────────────────────────────────────


class TestVectors:
    async def test_one_element_subarray_is_written_as_a_blob(self, any_client, any_cleanup):
        """A ``(1,)`` field is a vector: it is stored as a blob, not as the scalar 0.14.x wrote."""
        key = (NS, SET, 401)
        any_cleanup.append(key)
        dtype = np.dtype([("_key", "i8"), ("f", "f4", (1,)), ("i", "i8", (1,))])
        data = np.zeros(1, dtype=dtype)
        data[0] = (401, [1.5], [-7])

        await invoke(any_client, "batch_write_numpy", data, NS, SET)

        bins = (await invoke(any_client, "get", key)).bins
        assert isinstance(bins["f"], bytes) and len(bins["f"]) == 4
        assert isinstance(bins["i"], bytes) and len(bins["i"]) == 8
        assert np.frombuffer(bins["f"], dtype="=f4").tolist() == [1.5]
        assert np.frombuffer(bins["i"], dtype="=i8").tolist() == [-7]
        read = await _read(any_client, [key], np.dtype([("f", "f4", (1,)), ("i", "i8", (1,))]))
        assert read.batch_records[0]["f"].tolist() == [1.5]
        assert read.batch_records[0]["i"].tolist() == [-7]

    async def test_vectors_round_trip_exactly(self, any_client, any_cleanup):
        fields = [("vec", "f8", (4,)), ("mat", "i4", (2, 3)), ("half", "f2", (3,)), ("u", "u2", (5,))]
        dtype = np.dtype([("_key", "i8"), *fields])
        rng = np.random.default_rng(1234)
        data = np.zeros(3, dtype=dtype)
        data["_key"] = [411, 412, 413]
        data["vec"] = rng.standard_normal((3, 4))
        data["mat"] = rng.integers(-(2**31), 2**31 - 1, size=(3, 2, 3))
        data["half"] = rng.standard_normal((3, 3)).astype("f2")
        data["u"] = rng.integers(0, 2**16, size=(3, 5))
        keys = _keys([411, 412, 413])
        any_cleanup.extend(keys)

        result = await invoke(any_client, "batch_write_numpy", data, NS, SET)
        assert [br.result for br in result.batch_records] == [0, 0, 0]

        bins = (await invoke(any_client, "get", keys[0])).bins
        assert {name: len(bins[name]) for name, *_ in fields} == {"vec": 32, "mat": 24, "half": 6, "u": 10}
        read = await _read(any_client, keys, np.dtype(fields))
        for name, *_ in fields:
            np.testing.assert_array_equal(read.batch_records[name], data[name])

    @pytest.mark.parametrize(
        ("stored", "field", "expected"),
        [
            pytest.param(7.25, ("v", "f4", (1,)), [7.25], id="float"),
            pytest.param(-7, ("v", "i8", (1,)), [-7], id="int"),
            pytest.param(7, ("v", "f8", (1,)), [7.0], id="int_into_float"),
        ],
    )
    async def test_legacy_scalar_reads_as_a_length_one_vector(self, any_client, any_cleanup, stored, field, expected):
        """Data written by 0.14.x for a ``(1,)`` field is a plain scalar; it must stay readable."""
        key = (NS, SET, 421)
        await _put(any_client, any_cleanup, key, {"v": stored})

        read = await _read(any_client, [key], np.dtype([field]))

        assert read.result_codes.tolist() == [0]
        assert read.batch_records[0]["v"].shape == (1,)
        assert read.batch_records[0]["v"].tolist() == expected

    @pytest.mark.parametrize(
        ("stored", "field", "detail"),
        [
            pytest.param(
                b"\x00" * 8, ("v", "f8", (4,)), "the stored blob has 8 bytes, the dtype expects 32", id="short_blob"
            ),
            pytest.param(
                b"\x00" * 40, ("v", "f8", (4,)), "the stored blob has 40 bytes, the dtype expects 32", id="long_blob"
            ),
            pytest.param(
                b"\x00" * 3, ("v", "f4", (1,)), "the stored blob has 3 bytes, the dtype expects 4", id="short_blob_1"
            ),
            pytest.param(
                1.5, ("v", "f8", (4,)), "the stored value is a scalar, the dtype expects 4 elements", id="scalar"
            ),
            pytest.param(
                3, ("v", "i4", (2, 3)), "the stored value is a scalar, the dtype expects 6 elements", id="scalar_2d"
            ),
        ],
    )
    async def test_vector_length_mismatch_is_an_error(self, any_client, any_cleanup, stored, field, detail):
        """A blob is never truncated or zero-padded into a vector, and a scalar fills only a ``(1,)`` field."""
        key = (NS, SET, 431)
        await _put(any_client, any_cleanup, key, {"v": stored})
        handle = await invoke(any_client, "batch_read", [key])

        with pytest.raises(ValueError, match="vector length mismatch for field 'v'") as excinfo:
            handle.to_numpy(np.dtype([field]))
        assert detail in str(excinfo.value)


# ── fixed-width bytes ───────────────────────────────────────────


class TestFixedWidthBytes:
    async def test_read_pads_shorter_and_truncates_longer_values(self, any_client, any_cleanup):
        key = (NS, SET, 441)
        await _put(
            any_client, any_cleanup, key, {"short": b"abc", "exact": b"abcd", "long": b"abcdefghij", "text": "hello"}
        )
        dtype = np.dtype([("short", "S8"), ("exact", "S4"), ("long", "S4"), ("text", "S8")])

        rows = (await _read(any_client, [key], dtype)).batch_records

        assert rows[0].tolist() == (b"abc", b"abcd", b"abcd", b"hello")
        # The raw field bytes show the null padding NumPy strips on access.
        assert rows["short"].tobytes() == b"abc\x00\x00\x00\x00\x00"
        assert rows["text"].tobytes() == b"hello\x00\x00\x00"

    async def test_write_stores_the_full_field_width(self, any_client, any_cleanup):
        """An ``S<N>`` bin is stored with its padding; only the ``_key`` field is trimmed."""
        key = (NS, SET, b"k-451")
        any_cleanup.append(key)
        data = np.array([(b"k-451", b"abc")], dtype=[("_key", "S8"), ("name", "S8")])

        await invoke(any_client, "batch_write_numpy", data, NS, SET)

        assert (await invoke(any_client, "get", key)).bins == {"name": b"abc\x00\x00\x00\x00\x00"}
        read = await _read(any_client, [key], np.dtype([("name", "S8")]))
        assert read.batch_records[0]["name"] == b"abc"


# ── floats ──────────────────────────────────────────────────────

F16_MAX = float(np.finfo(np.float16).max)
F32_MAX = float(np.finfo(np.float32).max)


class TestFloatRange:
    @pytest.mark.parametrize(
        ("stored", "field", "width"),
        [
            pytest.param(70000.0, ("v", "f2"), "f16", id="f2"),
            pytest.param(-70000.0, ("v", "f2"), "f16", id="f2_negative"),
            pytest.param(65505.0, ("v", "f2"), "f16", id="f2_just_above_max"),
            pytest.param(70000, ("v", "f2"), "f16", id="f2_from_int"),
            pytest.param(70000.0, ("v", "f2", (1,)), "f16", id="f2_legacy_scalar_vector"),
            pytest.param(1e39, ("v", "f4"), "f32", id="f4"),
            pytest.param(-1e39, ("v", "f4"), "f32", id="f4_negative"),
            pytest.param(3.5e38, ("v", "f4"), "f32", id="f4_just_above_max"),
        ],
    )
    async def test_finite_overflow_raises(self, any_client, any_cleanup, stored, field, width):
        """A finite value that would become ±inf in a narrow float is an error, not a silent inf."""
        key = (NS, SET, 461)
        await _put(any_client, any_cleanup, key, {"v": stored})
        handle = await invoke(any_client, "batch_read", [key])

        with pytest.raises(OverflowError, match=f"does not fit in {width} for field 'v'"):
            handle.to_numpy(np.dtype([field]))

    @pytest.mark.parametrize(
        ("stored", "kind"),
        [
            pytest.param(F16_MAX, "f2", id="f2_max"),
            pytest.param(-F16_MAX, "f2", id="f2_min"),
            pytest.param(F32_MAX, "f4", id="f4_max"),
            pytest.param(-F32_MAX, "f4", id="f4_min"),
        ],
    )
    async def test_largest_finite_value_still_fits(self, any_client, any_cleanup, stored, kind):
        key = (NS, SET, 462)
        await _put(any_client, any_cleanup, key, {"v": stored})

        read = await _read(any_client, [key], np.dtype([("v", kind)]))

        assert float(read.batch_records[0]["v"]) == stored

    @pytest.mark.parametrize("kind", ["f2", "f4", "f8"])
    async def test_nan_and_infinities_are_preserved(self, any_client, any_cleanup, kind):
        key = (NS, SET, 463)
        await _put(any_client, any_cleanup, key, {"nan": math.nan, "inf": math.inf, "ninf": -math.inf})

        row = (await _read(any_client, [key], np.dtype([("nan", kind), ("inf", kind), ("ninf", kind)]))).batch_records[
            0
        ]

        assert math.isnan(row["nan"])
        assert row["inf"] == math.inf
        assert row["ninf"] == -math.inf


# ── keys and rows ───────────────────────────────────────────────

V_DTYPE = np.dtype([("v", "i8")])


class TestKeysAndRows:
    async def test_row_i_is_request_i_including_misses(self, any_client, any_cleanup):
        for k in (502, 504, 505):
            await _put(any_client, any_cleanup, (NS, SET, k), {"v": k * 10})
        requested = [501, 502, 503, 504, 505, 506]

        result = await _read(any_client, _keys(requested), V_DTYPE)

        assert len(result) == len(requested)
        assert result.result_codes.tolist() == [2, 0, 2, 0, 0, 2]
        assert result.batch_records["v"].tolist() == [0, 5020, 0, 5040, 5050, 0]
        assert [int(g) > 0 for g in result.meta["gen"]] == [False, True, False, True, True, False]
        # Every row requested with a user key is indexed, misses included.
        for position, k in enumerate(requested):
            assert k in result
            assert result.get(k)["v"] == result.batch_records[position]["v"]

    async def test_filtered_out_rows_keep_their_position_and_code(self, any_client, any_cleanup):
        """A row the filter expression excluded (27) stays in place next to found (0) and missing (2) rows."""
        for k, v in ((511, 10), (512, 20), (513, 30)):
            await _put(any_client, any_cleanup, (NS, SET, k), {"v": v})
        expression = exp.gt(exp.int_bin("v"), exp.int_val(15))

        handle = await invoke(
            any_client, "batch_read", _keys([511, 519, 512, 513]), policy={"filter_expression": expression}
        )
        result = handle.to_numpy(V_DTYPE)

        assert result.result_codes.tolist() == [27, 2, 0, 0]
        assert result.batch_records["v"].tolist() == [0, 0, 20, 30]

    async def test_digest_only_rows_are_reachable_by_position_only(self, any_client, any_cleanup):
        """No key is invented for a digest-only row.

        The native path used to index such a row under ``"__no_user_key_<i>__"``
        and the pure-Python path under the row index ``i``, which could shadow
        a real integer key equal to that position.
        """
        for k in (0, 1, 611):
            await _put(any_client, any_cleanup, (NS, SET, k), {"v": 1000 + k})
        digests = await invoke(any_client, "batch_read", [(NS, SET, 611), (NS, SET, 699)])
        digest_611, digest_699 = (br.key[3] for br in digests.batch_records)
        requested = [(NS, SET, None, digest_611), (NS, SET, 1), (NS, SET, 0), (NS, SET, None, digest_699)]

        result = await _read(any_client, requested, V_DTYPE)

        assert result.result_codes.tolist() == [0, 0, 0, 2]
        assert result.batch_records["v"].tolist() == [1611, 1001, 1000, 0]
        # The real integer keys point at their own rows, not at the row with that index.
        assert result.get(0)["v"] == 1000
        assert result.get(1)["v"] == 1001
        # The digest-only rows are not reachable through the key index.
        for absent in (611, 699, 3, None, digest_611, digest_699, "__no_user_key_0__", "__no_user_key_3__"):
            assert absent not in result
            with pytest.raises(KeyError):
                result.get(absent)
        assert result._map == {1: 1, 0: 2}

    async def test_repeated_user_key_points_at_the_last_row(self, any_client, any_cleanup):
        for k in (701, 702):
            await _put(any_client, any_cleanup, (NS, SET, k), {"v": k})

        result = await _read(any_client, _keys([701, 702, 701]), V_DTYPE)

        assert result.result_codes.tolist() == [0, 0, 0]
        assert result.batch_records["v"].tolist() == [701, 702, 701]
        # Both rows hold the same record; mark the first to see which one get() returns.
        result.batch_records["v"][0] = -1
        assert result.get(701)["v"] == 701
        assert result.get(702)["v"] == 702

    async def test_same_user_key_in_two_sets_points_at_the_last_row(self, any_client, any_cleanup):
        await _put(any_client, any_cleanup, (NS, SET, 801), {"v": 1})
        await _put(any_client, any_cleanup, (NS, SET_B, 801), {"v": 2})

        result = await _read(any_client, [(NS, SET, 801), (NS, SET_B, 801)], V_DTYPE)

        assert result.result_codes.tolist() == [0, 0]
        assert result.batch_records["v"].tolist() == [1, 2]
        assert result.get(801)["v"] == 2


class TestTheKeyFieldIsOneValue:
    """A sub-array key was written under the bytes of its elements, trailing zeros cut off.

    ``('_key', 'i8', (1,))`` holding 5 went to the record of the bytes key
    ``b"\\x05"``, not to the integer key 5 it addressed up to 0.14.x, and the
    keys ``[1, 0]`` and ``[1]`` were one record.
    """

    @pytest.mark.parametrize(
        "key_type",
        [("i8", (1,)), ("i8", (2,)), ("S4", (2,)), ([("a", "i4"), ("b", "i4")],)],
        ids=["one_int", "two_ints", "two_bytes", "nested_structure"],
    )
    async def test_anything_else_is_refused_and_nothing_is_written(self, any_client, any_cleanup, key_type):
        # Where the rows went before this was refused: the bytes of the key's
        # elements with the trailing zeros cut off, and the all-zero key.
        strays = [(NS, SET, stray) for stray in (b"", b"\x05", 0)]
        any_cleanup.extend(strays)
        await invoke(any_client, "batch_remove", strays)
        await _put(any_client, any_cleanup, (NS, SET, 5), {"v": -1})
        data = np.zeros(2, np.dtype([("_key", *key_type), ("v", "i4")]))
        data["v"] = [10, 20]

        with pytest.raises(TypeError, match="the key field '_key' must be a scalar integer or bytes field"):
            await invoke(any_client, "batch_write_numpy", data, NS, SET)

        assert (await invoke(any_client, "get", (NS, SET, 5))).bins == {"v": -1}
        assert await _result_codes(any_client, strays) == [2, 2, 2]

    async def test_a_custom_key_field_is_held_to_the_same_rule(self, any_client, any_cleanup):
        data = np.zeros(1, np.dtype([("id", "i8", (1,)), ("v", "i4")]))

        with pytest.raises(TypeError, match="the key field 'id' must be a scalar"):
            await invoke(any_client, "batch_write_numpy", data, NS, SET, key_field="id")

    async def test_a_sub_array_bin_next_to_a_scalar_key_is_still_a_vector(self, any_client, any_cleanup):
        data = np.zeros(1, np.dtype([("_key", "i8"), ("vec", "f4", (3,))]))
        data["_key"] = [9001]
        data["vec"] = [[1.5, 2.5, 3.5]]
        any_cleanup.append((NS, SET, 9001))

        await invoke(any_client, "batch_write_numpy", data, NS, SET)

        result = await _read(any_client, _keys([9001]), np.dtype([("vec", "f4", (3,))]))
        assert result.batch_records["vec"].tolist() == [[1.5, 2.5, 3.5]]


class TestAFieldOfNoBytes:
    """NumPy has ``S0``, ``V0`` and ``(0,)`` sub-arrays. There is nothing in them to read or write."""

    @pytest.mark.parametrize("empty", [("e", "S0"), ("e", "V0"), ("e", "f4", (0,))], ids=["S0", "V0", "no_elements"])
    async def test_it_is_written_and_read_next_to_real_fields(self, any_client, any_cleanup, empty):
        data = np.zeros(2, np.dtype([("_key", "i8"), empty, ("v", "i4")]))
        data["_key"] = [9501, 9502]
        data["v"] = [1, 2]
        any_cleanup.extend(_keys([9501, 9502]))

        written = await invoke(any_client, "batch_write_numpy", data, NS, SET)
        result = await _read(any_client, _keys([9501, 9502]), np.dtype([empty, ("v", "i4")]))

        assert [row.result for row in written.batch_records] == [0, 0]
        assert result.result_codes.tolist() == [0, 0]
        assert result.batch_records["v"].tolist() == [1, 2]
        assert result.batch_records["e"].nbytes == 0


class TestBytesOfEveryKind:
    """What ``get()`` returns as ``bytes`` goes into a bytes field, whatever the server calls it."""

    @pytest.mark.parametrize("spec", [("h", "S16"), ("h", "V300")], ids=["S16", "V300"])
    async def test_an_hll_bin(self, any_client, any_cleanup, spec):
        key = (NS, SET, 9101)
        await _put(any_client, any_cleanup, key, {"ok": 1})
        await invoke(any_client, "operate", key, [hll.hll_add("h", ["a", "b"], 8)])
        stored = (await invoke(any_client, "get", key)).bins["h"]
        assert isinstance(stored, bytes)

        result = await _read(any_client, [key], np.dtype([spec, ("ok", "i4")]))

        width = result.batch_records.dtype["h"].itemsize
        assert result.result_codes.tolist() == [0]
        assert result.batch_records["ok"].tolist() == [1]
        assert result.batch_records["h"].tobytes() == stored[:width].ljust(width, b"\0")

    async def test_an_hll_bin_into_a_vector_of_its_exact_length(self, any_client, any_cleanup):
        key = (NS, SET, 9102)
        await _put(any_client, any_cleanup, key, {"ok": 1})
        await invoke(any_client, "operate", key, [hll.hll_add("h", ["a", "b"], 8)])
        stored = (await invoke(any_client, "get", key)).bins["h"]

        result = await _read(any_client, [key], np.dtype([("h", "u1", (len(stored),))]))

        assert result.batch_records["h"].tobytes() == stored


def _in_a_child(body: str) -> list[str]:
    """Run ``body`` in an interpreter of its own and return what it printed.

    The cases below guard a raw-pointer copy. If the guard went missing the
    copy would run outside its buffer, and that is not something to try inside
    the process that runs the rest of the suite.
    """
    script = textwrap.dedent(
        f"""
            import numpy as np
            import aerospike_py

            client = aerospike_py.client({AEROSPIKE_CONFIG!r}).connect()
            NS, SET = {NS!r}, {SET!r}
            """
    ) + textwrap.dedent(body)
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip().splitlines()


class TestTheLayoutIsNumpysOwn:
    def test_to_numpy_writes_through_the_dtype_numpy_allocates(self, client, cleanup):
        """A dtype-like object once had its own ``fields`` believed over the array NumPy made of it."""
        key = (NS, SET, 9201)
        cleanup.append(key)
        client.put(key, {"v": 7})

        printed = _in_a_child(
            """
            class Lying:
                dtype = np.dtype([("v", "i1")])  # what np.zeros(n, Lying()) allocates: 1 byte a row
                names = ("v",)
                fields = {"v": (np.dtype("i8"), 4096)}  # what it claims: 8 bytes, 4096 into the row
                itemsize = 8192
                kind = "V"

            handle = client.batch_read([(NS, SET, 9201)] * 64)
            result = handle.to_numpy(Lying())
            print(result.batch_records.dtype.itemsize, result.batch_records.nbytes)
            print(result.batch_records["v"].tolist() == [7] * 64)
            """
        )

        assert printed == ["1 64", "True"]

    def test_batch_write_numpy_reads_the_rows_the_array_has(self, client, cleanup):
        """An array subclass once had its ``len()`` believed over its buffer."""
        cleanup.extend((NS, SET, k) for k in range(9300, 9310))

        printed = _in_a_child(
            """
            class Longer(np.ndarray):
                def __len__(self):
                    return 1_000_000

            data = np.zeros(2, np.dtype([("_key", "i8"), ("v", "i4")])).view(Longer)
            data["_key"] = [9300, 9301]
            data["v"] = [1, 2]
            result = client.batch_write_numpy(data, NS, SET)
            print(len(result.batch_records), [row.result for row in result.batch_records])
            print([client.get((NS, SET, k)).bins for k in (9300, 9301)])
            """
        )

        assert printed == ["2 [0, 0]", "[{'v': 1}, {'v': 2}]"]

    def test_a_record_array_is_written_like_the_array_it_is(self, client, cleanup):
        cleanup.extend((NS, SET, k) for k in (9401, 9402))
        data = np.rec.array([(9401, 1), (9402, 2)], dtype=[("_key", "i8"), ("v", "i4")])

        result = client.batch_write_numpy(data, NS, SET)

        assert [row.result for row in result.batch_records] == [0, 0]
        assert [client.get((NS, SET, k)).bins for k in (9401, 9402)] == [{"v": 1}, {"v": 2}]
