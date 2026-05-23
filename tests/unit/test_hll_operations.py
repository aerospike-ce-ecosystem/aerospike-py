"""Unit tests for hll_operations helpers (no server required)."""

import pytest

from aerospike_py import hll_operations
from aerospike_py.hll_operations import (
    hll_add,
    hll_describe,
    hll_fold,
    hll_get_count,
    hll_get_intersect_count,
    hll_get_similarity,
    hll_get_union,
    hll_get_union_count,
    hll_init,
    hll_set_union,
)


class TestHLLOperations:
    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,extra",
        [
            (
                hll_init,
                ("mybin", 8),
                {},
                3001,
                {"index_bit_count": 8},
            ),
            (
                hll_init,
                ("mybin", 12),
                {"minhash_bit_count": 16},
                3001,
                {"index_bit_count": 12, "minhash_bit_count": 16},
            ),
            (
                hll_add,
                ("mybin", ["a", "b", "c"]),
                {},
                3002,
                {"val": ["a", "b", "c"]},
            ),
            (
                hll_add,
                ("mybin", ["x", "y"]),
                {"index_bit_count": 8},
                3002,
                {"val": ["x", "y"], "index_bit_count": 8},
            ),
            (
                hll_add,
                ("mybin", ["x"]),
                {"index_bit_count": 8, "minhash_bit_count": 16},
                3002,
                {"val": ["x"], "index_bit_count": 8, "minhash_bit_count": 16},
            ),
            (
                hll_get_count,
                ("mybin",),
                {},
                3003,
                {},
            ),
            (
                hll_get_union,
                ("mybin", [b"\x00\x01"]),
                {},
                3004,
                {"val": [b"\x00\x01"]},
            ),
            (
                hll_get_union_count,
                ("mybin", [b"\x00\x01"]),
                {},
                3005,
                {"val": [b"\x00\x01"]},
            ),
            (
                hll_get_intersect_count,
                ("mybin", [b"\x00\x01"]),
                {},
                3006,
                {"val": [b"\x00\x01"]},
            ),
            (
                hll_get_similarity,
                ("mybin", [b"\x00\x01"]),
                {},
                3007,
                {"val": [b"\x00\x01"]},
            ),
            (
                hll_describe,
                ("mybin",),
                {},
                3008,
                {},
            ),
            (
                hll_fold,
                ("mybin", 4),
                {},
                3009,
                {"index_bit_count": 4},
            ),
            (
                hll_set_union,
                ("mybin", [b"\x00\x01"]),
                {},
                3010,
                {"val": [b"\x00\x01"]},
            ),
        ],
        ids=[
            "hll_init_basic",
            "hll_init_with_minhash",
            "hll_add_basic",
            "hll_add_with_index",
            "hll_add_with_index_and_minhash",
            "hll_get_count",
            "hll_get_union",
            "hll_get_union_count",
            "hll_get_intersect_count",
            "hll_get_similarity",
            "hll_describe",
            "hll_fold",
            "hll_set_union",
        ],
    )
    def test_hll_operation_structure(self, func, args, kwargs, expected_op, extra):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    def test_hll_init_no_minhash_omits_key(self):
        op = hll_init("mybin", 8)
        assert "minhash_bit_count" not in op

    def test_hll_add_no_index_omits_key(self):
        op = hll_add("mybin", ["a"])
        assert "index_bit_count" not in op
        assert "minhash_bit_count" not in op

    def test_hll_init_with_policy(self):
        op = hll_init("mybin", 8, policy={"flags": 1})
        assert op["hll_policy"]["flags"] == 1

    def test_hll_add_with_policy(self):
        op = hll_add("mybin", ["a", "b"], policy={"flags": 4})
        assert op["hll_policy"]["flags"] == 4

    def test_hll_set_union_with_policy(self):
        op = hll_set_union("mybin", [b"\x00"], policy={"flags": 8})
        assert op["hll_policy"]["flags"] == 8

    def test_hll_init_no_policy_omits_key(self):
        op = hll_init("mybin", 8)
        assert "hll_policy" not in op

    def test_hll_set_union_no_policy_omits_key(self):
        op = hll_set_union("mybin", [b"\x00"])
        assert "hll_policy" not in op

    def test_hll_ops_facade_always_emits_val(self):
        """Regression: hll_add / hll_get_union / hll_get_union_count /
        hll_get_intersect_count / hll_get_similarity / hll_set_union op dicts
        must always include `val`.

        At the Rust dispatch layer (operations.rs OP_HLL_{ADD,GET_UNION,
        GET_UNION_COUNT,GET_INTERSECT_COUNT,GET_SIMILARITY,SET_UNION} arms), a
        missing `val` raises ValueError rather than silently defaulting to
        `Value::Nil` (which `values_from_list` would coerce into an empty list,
        producing a no-op `hll_add` or "compared against zero HLL bins" result
        the caller could not distinguish from a genuinely empty input). The
        Python facade signatures already require `values` as a positional
        argument; this test asserts both that the emitted op carries the value
        through and that the facade has no default that would let a caller omit
        it.
        """
        emitting = [
            (hll_add, ("mybin", ["a", "b"]), 3002),
            (hll_get_union, ("mybin", [b"\x00"]), 3004),
            (hll_get_union_count, ("mybin", [b"\x00"]), 3005),
            (hll_get_intersect_count, ("mybin", [b"\x00"]), 3006),
            (hll_get_similarity, ("mybin", [b"\x00"]), 3007),
            (hll_set_union, ("mybin", [b"\x00"]), 3010),
        ]
        for func, args, expected_op in emitting:
            op = func(*args)
            assert op["op"] == expected_op
            assert "val" in op, f"{func.__name__} must emit 'val' in op dict"
            assert op["val"] == args[-1]

        # The facade has no default that would let a caller produce a
        # value-less op dict for any of these ops.
        with pytest.raises(TypeError):
            hll_add("mybin")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            hll_get_union("mybin")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            hll_get_union_count("mybin")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            hll_get_intersect_count("mybin")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            hll_get_similarity("mybin")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            hll_set_union("mybin")  # type: ignore[call-arg]


class TestHLLModuleAccess:
    """Test that the module is accessible from the package."""

    def test_hll_operations_module(self):
        assert hasattr(hll_operations, "hll_init")
        assert hasattr(hll_operations, "hll_add")
        assert hasattr(hll_operations, "hll_get_count")
        assert hasattr(hll_operations, "hll_describe")
        assert hasattr(hll_operations, "hll_fold")
        assert hasattr(hll_operations, "hll_set_union")
        assert hasattr(hll_operations, "hll_get_union")
        assert hasattr(hll_operations, "hll_get_union_count")
        assert hasattr(hll_operations, "hll_get_intersect_count")
        assert hasattr(hll_operations, "hll_get_similarity")
