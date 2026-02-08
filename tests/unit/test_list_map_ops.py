"""Unit tests for list_operations and map_operations helpers (no server required)."""

from aerospike_py import list_operations, map_operations
from aerospike_py.list_operations import (
    list_append,
    list_append_items,
    list_clear,
    list_get,
    list_get_by_index,
    list_get_by_rank,
    list_get_by_rank_range,
    list_get_range,
    list_increment,
    list_insert,
    list_pop,
    list_pop_range,
    list_remove,
    list_remove_by_rank,
    list_remove_by_rank_range,
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
    map_size,
)


class TestListOperations:
    def test_list_append(self):
        op = list_append("mybin", 42)
        assert op["op"] == 1001
        assert op["bin"] == "mybin"
        assert op["val"] == 42

    def test_list_append_with_policy(self):
        op = list_append("mybin", "val", policy={"order": 1, "flags": 0})
        assert op["list_policy"]["order"] == 1

    def test_list_append_items(self):
        op = list_append_items("mybin", [1, 2, 3])
        assert op["op"] == 1002
        assert op["val"] == [1, 2, 3]

    def test_list_insert(self):
        op = list_insert("mybin", 0, "hello")
        assert op["op"] == 1003
        assert op["index"] == 0
        assert op["val"] == "hello"

    def test_list_pop(self):
        op = list_pop("mybin", 2)
        assert op["op"] == 1005
        assert op["index"] == 2

    def test_list_pop_range(self):
        op = list_pop_range("mybin", 0, 3)
        assert op["op"] == 1006
        assert op["count"] == 3

    def test_list_remove(self):
        op = list_remove("mybin", 1)
        assert op["op"] == 1007
        assert op["index"] == 1

    def test_list_remove_range(self):
        op = list_remove_range("mybin", 0, 5)
        assert op["op"] == 1008
        assert op["count"] == 5

    def test_list_set(self):
        op = list_set("mybin", 3, "value")
        assert op["op"] == 1009
        assert op["index"] == 3

    def test_list_trim(self):
        op = list_trim("mybin", 1, 3)
        assert op["op"] == 1010

    def test_list_clear(self):
        op = list_clear("mybin")
        assert op["op"] == 1011

    def test_list_size(self):
        op = list_size("mybin")
        assert op["op"] == 1012

    def test_list_get(self):
        op = list_get("mybin", 0)
        assert op["op"] == 1013
        assert op["index"] == 0

    def test_list_get_range(self):
        op = list_get_range("mybin", 0, 5)
        assert op["op"] == 1014
        assert op["count"] == 5

    def test_list_get_by_index(self):
        op = list_get_by_index("mybin", 2, return_type=7)
        assert op["op"] == 1016
        assert op["return_type"] == 7

    def test_list_get_by_rank(self):
        op = list_get_by_rank("mybin", 0, return_type=7)
        assert op["op"] == 1018
        assert op["rank"] == 0
        assert op["return_type"] == 7

    def test_list_get_by_rank_range(self):
        op = list_get_by_rank_range("mybin", 1, return_type=5, count=3)
        assert op["op"] == 1019
        assert op["rank"] == 1
        assert op["return_type"] == 5
        assert op["count"] == 3

    def test_list_get_by_rank_range_no_count(self):
        op = list_get_by_rank_range("mybin", 0, return_type=7)
        assert op["op"] == 1019
        assert op["rank"] == 0
        assert "count" not in op

    def test_list_remove_by_rank(self):
        op = list_remove_by_rank("mybin", 2, return_type=0)
        assert op["op"] == 1027
        assert op["rank"] == 2
        assert op["return_type"] == 0

    def test_list_remove_by_rank_range(self):
        op = list_remove_by_rank_range("mybin", 0, return_type=5, count=2)
        assert op["op"] == 1028
        assert op["rank"] == 0
        assert op["return_type"] == 5
        assert op["count"] == 2

    def test_list_remove_by_rank_range_no_count(self):
        op = list_remove_by_rank_range("mybin", 1, return_type=0)
        assert op["op"] == 1028
        assert op["rank"] == 1
        assert "count" not in op

    def test_list_increment(self):
        op = list_increment("mybin", 0, 5)
        assert op["op"] == 1029
        assert op["val"] == 5

    def test_list_sort(self):
        op = list_sort("mybin", sort_flags=2)
        assert op["op"] == 1030
        assert op["val"] == 2


class TestMapOperations:
    def test_map_put(self):
        op = map_put("mybin", "key1", "value1")
        assert op["op"] == 2002
        assert op["map_key"] == "key1"
        assert op["val"] == "value1"

    def test_map_put_with_policy(self):
        op = map_put("mybin", "k", "v", policy={"order": 1, "write_mode": 0})
        assert op["map_policy"]["order"] == 1

    def test_map_put_items(self):
        op = map_put_items("mybin", {"a": 1, "b": 2})
        assert op["op"] == 2003
        assert op["val"] == {"a": 1, "b": 2}

    def test_map_increment(self):
        op = map_increment("mybin", "counter", 5)
        assert op["op"] == 2004
        assert op["map_key"] == "counter"

    def test_map_decrement(self):
        op = map_decrement("mybin", "counter", 3)
        assert op["op"] == 2005

    def test_map_clear(self):
        op = map_clear("mybin")
        assert op["op"] == 2006

    def test_map_remove_by_key(self):
        op = map_remove_by_key("mybin", "key1", return_type=0)
        assert op["op"] == 2007
        assert op["return_type"] == 0

    def test_map_size(self):
        op = map_size("mybin")
        assert op["op"] == 2017

    def test_map_get_by_key(self):
        op = map_get_by_key("mybin", "key1", return_type=7)
        assert op["op"] == 2018
        assert op["return_type"] == 7

    def test_map_get_by_value(self):
        op = map_get_by_value("mybin", 42, return_type=5)
        assert op["op"] == 2020

    def test_map_get_by_index(self):
        op = map_get_by_index("mybin", 0, return_type=7)
        assert op["op"] == 2022

    def test_map_get_by_rank(self):
        op = map_get_by_rank("mybin", 0, return_type=7)
        assert op["op"] == 2024
        assert op["rank"] == 0
        assert op["return_type"] == 7

    def test_map_get_by_rank_range(self):
        op = map_get_by_rank_range("mybin", 1, return_type=5, count=3)
        assert op["op"] == 2025
        assert op["rank"] == 1
        assert op["return_type"] == 5
        assert op["count"] == 3

    def test_map_get_by_rank_range_no_count(self):
        op = map_get_by_rank_range("mybin", 0, return_type=7)
        assert op["op"] == 2025
        assert op["rank"] == 0
        assert "count" not in op

    def test_map_remove_by_rank(self):
        op = map_remove_by_rank("mybin", 2, return_type=0)
        assert op["op"] == 2015
        assert op["rank"] == 2
        assert op["return_type"] == 0

    def test_map_remove_by_rank_range(self):
        op = map_remove_by_rank_range("mybin", 0, return_type=5, count=2)
        assert op["op"] == 2016
        assert op["rank"] == 0
        assert op["return_type"] == 5
        assert op["count"] == 2

    def test_map_remove_by_rank_range_no_count(self):
        op = map_remove_by_rank_range("mybin", 1, return_type=0)
        assert op["op"] == 2016
        assert op["rank"] == 1
        assert "count" not in op


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
