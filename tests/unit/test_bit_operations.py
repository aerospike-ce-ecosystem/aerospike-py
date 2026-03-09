"""Unit tests for bit_operations helpers (no server required)."""

import pytest

from aerospike_py import bit_operations
from aerospike_py.bit_operations import (
    bit_add,
    bit_and,
    bit_count,
    bit_get,
    bit_get_int,
    bit_insert,
    bit_lscan,
    bit_lshift,
    bit_not,
    bit_or,
    bit_remove,
    bit_resize,
    bit_rscan,
    bit_rshift,
    bit_set,
    bit_set_int,
    bit_subtract,
    bit_xor,
)


class TestBitOperations:
    @pytest.mark.parametrize(
        "func,args,expected_op,extra",
        [
            (
                bit_resize,
                ("mybin", 4),
                3001,
                {"byte_size": 4},
            ),
            (
                bit_insert,
                ("mybin", 1, b"\xff\xc7"),
                3002,
                {"byte_offset": 1, "val": b"\xff\xc7"},
            ),
            (
                bit_remove,
                ("mybin", 2, 3),
                3003,
                {"byte_offset": 2, "byte_size": 3},
            ),
            (
                bit_set,
                ("mybin", 13, 3, b"\xe0"),
                3004,
                {"bit_offset": 13, "bit_size": 3, "val": b"\xe0"},
            ),
            (
                bit_or,
                ("mybin", 17, 6, b"\xa8"),
                3005,
                {"bit_offset": 17, "bit_size": 6, "val": b"\xa8"},
            ),
            (
                bit_xor,
                ("mybin", 17, 6, b"\xac"),
                3006,
                {"bit_offset": 17, "bit_size": 6, "val": b"\xac"},
            ),
            (
                bit_and,
                ("mybin", 23, 9, b"\x3c\x80"),
                3007,
                {"bit_offset": 23, "bit_size": 9, "val": b"\x3c\x80"},
            ),
            (
                bit_not,
                ("mybin", 25, 6),
                3008,
                {"bit_offset": 25, "bit_size": 6},
            ),
            (
                bit_lshift,
                ("mybin", 32, 8, 3),
                3009,
                {"bit_offset": 32, "bit_size": 8, "shift": 3},
            ),
            (
                bit_rshift,
                ("mybin", 0, 9, 1),
                3010,
                {"bit_offset": 0, "bit_size": 9, "shift": 1},
            ),
            (
                bit_get,
                ("mybin", 9, 5),
                3050,
                {"bit_offset": 9, "bit_size": 5},
            ),
            (
                bit_count,
                ("mybin", 20, 4),
                3051,
                {"bit_offset": 20, "bit_size": 4},
            ),
        ],
        ids=[
            "bit_resize",
            "bit_insert",
            "bit_remove",
            "bit_set",
            "bit_or",
            "bit_xor",
            "bit_and",
            "bit_not",
            "bit_lshift",
            "bit_rshift",
            "bit_get",
            "bit_count",
        ],
    )
    def test_bit_operation_structure(self, func, args, expected_op, extra):
        op = func(*args)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    def test_bit_resize_with_flags(self):
        op = bit_resize("mybin", 8, resize_flags=1)
        assert op["op"] == 3001
        assert op["byte_size"] == 8
        assert op["resize_flags"] == 1

    def test_bit_resize_default_no_resize_flags(self):
        op = bit_resize("mybin", 4)
        assert "resize_flags" not in op

    def test_bit_resize_with_policy(self):
        op = bit_resize("mybin", 4, policy=1)
        assert op["bit_policy"] == 1

    def test_bit_insert_with_policy(self):
        op = bit_insert("mybin", 0, b"\xff", policy=2)
        assert op["bit_policy"] == 2

    def test_bit_not_no_val(self):
        op = bit_not("mybin", 0, 8)
        assert "val" not in op

    def test_bit_add_structure(self):
        op = bit_add("mybin", 24, 16, 128, signed=True, action=2)
        assert op["op"] == 3011
        assert op["bit_offset"] == 24
        assert op["bit_size"] == 16
        assert op["val"] == 128
        assert op["signed"] is True
        assert op["action"] == 2

    def test_bit_subtract_structure(self):
        op = bit_subtract("mybin", 24, 16, 64, signed=False, action=4)
        assert op["op"] == 3012
        assert op["val"] == 64
        assert op["signed"] is False
        assert op["action"] == 4

    def test_bit_set_int_structure(self):
        op = bit_set_int("mybin", 1, 8, 127)
        assert op["op"] == 3013
        assert op["bit_offset"] == 1
        assert op["bit_size"] == 8
        assert op["val"] == 127

    def test_bit_lscan_structure(self):
        op = bit_lscan("mybin", 24, 8, True)
        assert op["op"] == 3052
        assert op["bit_offset"] == 24
        assert op["bit_size"] == 8
        assert op["val"] is True

    def test_bit_rscan_structure(self):
        op = bit_rscan("mybin", 32, 8, False)
        assert op["op"] == 3053
        assert op["val"] is False

    def test_bit_get_int_unsigned(self):
        op = bit_get_int("mybin", 8, 16)
        assert op["op"] == 3054
        assert op["bit_offset"] == 8
        assert op["bit_size"] == 16
        assert op["signed"] is False

    def test_bit_get_int_signed(self):
        op = bit_get_int("mybin", 8, 16, signed=True)
        assert op["signed"] is True

    def test_bit_add_defaults(self):
        op = bit_add("mybin", 0, 8, 1)
        assert op["signed"] is False
        assert op["action"] == 0
        assert "bit_policy" not in op

    def test_bit_subtract_with_policy(self):
        op = bit_subtract("mybin", 0, 8, 1, policy=4)
        assert op["bit_policy"] == 4


class TestModuleAccess:
    """Test that the module is accessible from the package."""

    def test_bit_operations_module(self):
        assert hasattr(bit_operations, "bit_resize")
        assert hasattr(bit_operations, "bit_get")
        assert hasattr(bit_operations, "bit_count")
        assert hasattr(bit_operations, "bit_or")
        assert hasattr(bit_operations, "bit_and")
        assert hasattr(bit_operations, "bit_get_int")

    def test_all_exports(self):
        expected = [
            "bit_resize",
            "bit_insert",
            "bit_remove",
            "bit_set",
            "bit_or",
            "bit_xor",
            "bit_and",
            "bit_not",
            "bit_lshift",
            "bit_rshift",
            "bit_add",
            "bit_subtract",
            "bit_set_int",
            "bit_get",
            "bit_count",
            "bit_lscan",
            "bit_rscan",
            "bit_get_int",
        ]
        for name in expected:
            assert name in bit_operations.__all__
