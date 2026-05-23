"""Unit tests for list_operations and map_operations helpers (no server required)."""

import pytest

from aerospike_py import list_operations, map_operations
from aerospike_py.list_operations import (
    list_append,
    list_append_items,
    list_clear,
    list_get,
    list_get_by_index,
    list_get_by_rank,
    list_get_by_rank_range,
    list_get_by_value,
    list_get_by_value_list,
    list_get_range,
    list_increment,
    list_insert,
    list_pop,
    list_pop_range,
    list_remove,
    list_remove_by_rank,
    list_remove_by_rank_range,
    list_remove_by_value,
    list_remove_by_value_list,
    list_remove_range,
    list_set,
    list_size,
    list_sort,
    list_trim,
)
from aerospike_py.map_operations import (
    map_clear,
    map_decrement,
    map_get_by_index,
    map_get_by_key,
    map_get_by_rank,
    map_get_by_rank_range,
    map_get_by_value,
    map_increment,
    map_put,
    map_put_items,
    map_remove_by_key,
    map_remove_by_rank,
    map_remove_by_rank_range,
    map_remove_by_value,
    map_remove_by_value_list,
    map_size,
)


class TestListOperations:
    @pytest.mark.parametrize(
        "func,args,expected_op,extra",
        [
            (list_append, ("mybin", 42), 1001, {"val": 42}),
            (list_append_items, ("mybin", [1, 2, 3]), 1002, {"val": [1, 2, 3]}),
            (list_insert, ("mybin", 0, "hello"), 1003, {"index": 0, "val": "hello"}),
            (list_pop, ("mybin", 2), 1005, {"index": 2}),
            (list_pop_range, ("mybin", 0, 3), 1006, {"count": 3}),
            (list_remove, ("mybin", 1), 1007, {"index": 1}),
            (list_remove_range, ("mybin", 0, 5), 1008, {"count": 5}),
            (list_set, ("mybin", 3, "value"), 1009, {"index": 3}),
            (list_trim, ("mybin", 1, 3), 1010, {}),
            (list_clear, ("mybin",), 1011, {}),
            (list_size, ("mybin",), 1012, {}),
            (list_get, ("mybin", 0), 1013, {"index": 0}),
            (list_get_range, ("mybin", 0, 5), 1014, {"count": 5}),
            (list_increment, ("mybin", 0, 5), 1029, {"val": 5}),
        ],
        ids=[
            "list_append",
            "list_append_items",
            "list_insert",
            "list_pop",
            "list_pop_range",
            "list_remove",
            "list_remove_range",
            "list_set",
            "list_trim",
            "list_clear",
            "list_size",
            "list_get",
            "list_get_range",
            "list_increment",
        ],
    )
    def test_list_operation_structure(self, func, args, expected_op, extra):
        op = func(*args)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    def test_list_sort(self):
        op = list_sort("mybin", sort_flags=2)
        assert op["op"] == 1030
        assert op["val"] == 2

    def test_list_trim_facade_always_emits_count(self):
        """Regression: `list_trim` op dict must always include `count`.

        At the Rust dispatch layer (operations.rs OP_LIST_TRIM arm), a missing
        `count` raises ValueError rather than silently defaulting to 0 (which
        would destructively truncate the list to empty). The Python facade
        signature already requires count, but assert the emitted op carries it
        through so direct dict callers and facade callers agree.
        """
        op = list_trim("mybin", 1, 3)
        assert op["op"] == 1010
        assert op["bin"] == "mybin"
        assert op["index"] == 1
        assert op["count"] == 3
        # The facade has no default that would let a caller produce a
        # list_trim without supplying count.
        with pytest.raises(TypeError):
            list_trim("mybin", 1)  # type: ignore[call-arg]

    def test_list_append_with_policy(self):
        op = list_append("mybin", "val", policy={"order": 1, "flags": 0})
        assert op["list_policy"]["order"] == 1

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,extra",
        [
            (
                list_get_by_index,
                ("mybin", 2),
                {"return_type": 7},
                1016,
                {"return_type": 7},
            ),
            (
                list_get_by_rank,
                ("mybin", 0),
                {"return_type": 7},
                1018,
                {"rank": 0, "return_type": 7},
            ),
            (
                list_remove_by_rank,
                ("mybin", 2),
                {"return_type": 0},
                1027,
                {"rank": 2, "return_type": 0},
            ),
        ],
        ids=[
            "list_get_by_index",
            "list_get_by_rank",
            "list_remove_by_rank",
        ],
    )
    def test_list_return_type_operations(self, func, args, kwargs, expected_op, extra):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,extra",
        [
            (
                list_get_by_rank_range,
                ("mybin", 1),
                {"return_type": 5, "count": 3},
                1019,
                {"rank": 1, "return_type": 5, "count": 3},
            ),
            (
                list_remove_by_rank_range,
                ("mybin", 0),
                {"return_type": 5, "count": 2},
                1028,
                {"rank": 0, "return_type": 5, "count": 2},
            ),
        ],
        ids=[
            "list_get_by_rank_range",
            "list_remove_by_rank_range",
        ],
    )
    def test_list_rank_range_with_count(self, func, args, kwargs, expected_op, extra):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,expected_rank",
        [
            (
                list_get_by_rank_range,
                ("mybin", 0),
                {"return_type": 7},
                1019,
                0,
            ),
            (
                list_remove_by_rank_range,
                ("mybin", 1),
                {"return_type": 0},
                1028,
                1,
            ),
        ],
        ids=[
            "list_get_by_rank_range_no_count",
            "list_remove_by_rank_range_no_count",
        ],
    )
    def test_list_rank_range_no_count(self, func, args, kwargs, expected_op, expected_rank):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["rank"] == expected_rank
        assert "count" not in op


class TestMapOperations:
    @pytest.mark.parametrize(
        "func,args,expected_op,extra",
        [
            (map_put, ("mybin", "key1", "value1"), 2002, {"map_key": "key1", "val": "value1"}),
            (map_put_items, ("mybin", {"a": 1, "b": 2}), 2003, {"val": {"a": 1, "b": 2}}),
            (map_increment, ("mybin", "counter", 5), 2004, {"map_key": "counter"}),
            (map_decrement, ("mybin", "counter", 3), 2005, {}),
            (map_clear, ("mybin",), 2006, {}),
            (map_size, ("mybin",), 2017, {}),
        ],
        ids=[
            "map_put",
            "map_put_items",
            "map_increment",
            "map_decrement",
            "map_clear",
            "map_size",
        ],
    )
    def test_map_operation_structure(self, func, args, expected_op, extra):
        op = func(*args)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    def test_map_put_with_policy(self):
        op = map_put("mybin", "k", "v", policy={"order": 1, "write_mode": 0})
        assert op["map_policy"]["order"] == 1

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,extra",
        [
            (
                map_remove_by_key,
                ("mybin", "key1"),
                {"return_type": 0},
                2007,
                {"return_type": 0},
            ),
            (
                map_get_by_key,
                ("mybin", "key1"),
                {"return_type": 7},
                2018,
                {"return_type": 7},
            ),
            (
                map_get_by_value,
                ("mybin", 42),
                {"return_type": 5},
                2020,
                {},
            ),
            (
                map_get_by_index,
                ("mybin", 0),
                {"return_type": 7},
                2022,
                {},
            ),
            (
                map_get_by_rank,
                ("mybin", 0),
                {"return_type": 7},
                2024,
                {"rank": 0, "return_type": 7},
            ),
            (
                map_remove_by_rank,
                ("mybin", 2),
                {"return_type": 0},
                2015,
                {"rank": 2, "return_type": 0},
            ),
        ],
        ids=[
            "map_remove_by_key",
            "map_get_by_key",
            "map_get_by_value",
            "map_get_by_index",
            "map_get_by_rank",
            "map_remove_by_rank",
        ],
    )
    def test_map_return_type_operations(self, func, args, kwargs, expected_op, extra):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,extra",
        [
            (
                map_get_by_rank_range,
                ("mybin", 1),
                {"return_type": 5, "count": 3},
                2025,
                {"rank": 1, "return_type": 5, "count": 3},
            ),
            (
                map_remove_by_rank_range,
                ("mybin", 0),
                {"return_type": 5, "count": 2},
                2016,
                {"rank": 0, "return_type": 5, "count": 2},
            ),
        ],
        ids=[
            "map_get_by_rank_range",
            "map_remove_by_rank_range",
        ],
    )
    def test_map_rank_range_with_count(self, func, args, kwargs, expected_op, extra):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        for k, v in extra.items():
            assert op[k] == v

    @pytest.mark.parametrize(
        "func,args,kwargs,expected_op,expected_rank",
        [
            (
                map_get_by_rank_range,
                ("mybin", 0),
                {"return_type": 7},
                2025,
                0,
            ),
            (
                map_remove_by_rank_range,
                ("mybin", 1),
                {"return_type": 0},
                2016,
                1,
            ),
        ],
        ids=[
            "map_get_by_rank_range_no_count",
            "map_remove_by_rank_range_no_count",
        ],
    )
    def test_map_rank_range_no_count(self, func, args, kwargs, expected_op, expected_rank):
        op = func(*args, **kwargs)
        assert op["op"] == expected_op
        assert op["rank"] == expected_rank
        assert "count" not in op

    def test_map_put_items_facade_always_emits_val(self):
        """Regression: `map_put_items` op dict must always include `val`.

        At the Rust dispatch layer (operations.rs OP_MAP_PUT_ITEMS arm), a
        missing `val` raises ValueError("map_put_items requires 'val'") rather
        than falling through to the catch-all `Value::Nil` arm and producing
        the misleading "map_put_items requires a dict value" error. The Python
        facade signature already requires `items`, but assert the emitted op
        carries it through so direct dict callers and facade callers agree.
        """
        op = map_put_items("mybin", {"a": 1, "b": 2})
        assert op["op"] == 2003
        assert op["bin"] == "mybin"
        assert "val" in op
        assert op["val"] == {"a": 1, "b": 2}
        # The facade has no default that would let a caller produce a
        # map_put_items op without supplying items.
        with pytest.raises(TypeError):
            map_put_items("mybin")  # type: ignore[call-arg]


class TestListMapByValueFacadeRequiresVal:
    """Regression: facade helpers for list/map BY_VALUE ops always emit `val`.

    At the Rust dispatch layer (operations.rs) the OP_LIST_GET_BY_VALUE,
    OP_LIST_GET_BY_VALUE_LIST, OP_LIST_REMOVE_BY_VALUE,
    OP_LIST_REMOVE_BY_VALUE_LIST, OP_MAP_GET_BY_VALUE, OP_MAP_REMOVE_BY_VALUE,
    and OP_MAP_REMOVE_BY_VALUE_LIST arms now raise ValueError("<op> requires
    'val'") for a missing `val` key instead of silently substituting
    `Value::Nil`. These tests assert the facade always supplies `val` and
    rejects a missing positional value (TypeError), so callers using the
    facade never hit the dispatch-level error in normal use.
    """

    @pytest.mark.parametrize(
        "func,expected_op,sample_val",
        [
            (list_get_by_value, 1015, 42),
            (list_remove_by_value, 1022, 42),
            (map_get_by_value, 2020, 42),
            (map_remove_by_value, 2010, 42),
        ],
        ids=[
            "list_get_by_value",
            "list_remove_by_value",
            "map_get_by_value",
            "map_remove_by_value",
        ],
    )
    def test_by_value_facade_emits_val(self, func, expected_op, sample_val):
        op = func("mybin", sample_val, return_type=0)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        assert "val" in op
        assert op["val"] == sample_val
        with pytest.raises(TypeError):
            func("mybin", return_type=0)  # type: ignore[call-arg]

    @pytest.mark.parametrize(
        "func,expected_op,sample_values",
        [
            (list_get_by_value_list, 1020, [1, 2, 3]),
            (list_remove_by_value_list, 1023, [1, 2, 3]),
            (map_remove_by_value_list, 2011, [1, 2, 3]),
        ],
        ids=[
            "list_get_by_value_list",
            "list_remove_by_value_list",
            "map_remove_by_value_list",
        ],
    )
    def test_by_value_list_facade_emits_val(self, func, expected_op, sample_values):
        op = func("mybin", sample_values, return_type=0)
        assert op["op"] == expected_op
        assert op["bin"] == "mybin"
        assert "val" in op
        assert op["val"] == sample_values
        with pytest.raises(TypeError):
            func("mybin", return_type=0)  # type: ignore[call-arg]


class TestModuleAccess:
    """Test that modules are accessible from the package."""

    def test_list_operations_module(self):
        assert hasattr(list_operations, "list_append")
        assert hasattr(list_operations, "list_size")
        assert hasattr(list_operations, "list_sort")

    def test_map_operations_module(self):
        assert hasattr(map_operations, "map_put")
        assert hasattr(map_operations, "map_size")
        assert hasattr(map_operations, "map_clear")
