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
