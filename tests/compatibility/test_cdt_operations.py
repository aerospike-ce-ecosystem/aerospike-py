"""CDT (Collection Data Type) operation compatibility tests.

Compares list and map CDT operations between aerospike-py (Rust) and the
official aerospike Python client, with special focus on:
- list_remove_by_value_range argument order (potential bug in operations.rs:449)
- Value range operations consistency across get/remove variants
"""

import pytest

import aerospike_py
from aerospike_py import list_operations as rust_lop
from aerospike_py import map_operations as rust_mop

aerospike = pytest.importorskip("aerospike")
from aerospike_helpers.operations import list_operations as off_lop  # noqa: E402
from aerospike_helpers.operations import map_operations as off_mop  # noqa: E402

NS = "test"
SET = "compat_cdt"


# ── List Append ────────────────────────────────────────────────────


class TestListAppendOperations:
    """Cross-verify list_append and list_append_items."""

    def test_rust_list_append_official_read(self, rust_client, official_client, cleanup):
        key = (NS, SET, "la_r2o")
        cleanup.append(key)

        rust_client.put(key, {"items": [1, 2, 3]})
        ops = [rust_lop.list_append("items", 4)]
        rust_client.operate(key, ops)

        _, _, bins = official_client.get(key)
        assert bins["items"] == [1, 2, 3, 4]

    def test_official_list_append_rust_read(self, rust_client, official_client, cleanup):
        key = (NS, SET, "la_o2r")
        cleanup.append(key)

        official_client.put(key, {"items": [1, 2, 3]})
        ops = [off_lop.list_append("items", 4)]
        official_client.operate(key, ops)

        _, _, bins = rust_client.get(key)
        assert bins["items"] == [1, 2, 3, 4]

    def test_list_append_items_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lai_cross")
        cleanup.append(key)

        rust_client.put(key, {"items": [1]})
        ops = [rust_lop.list_append_items("items", [2, 3, 4])]
        rust_client.operate(key, ops)

        _, _, bins = official_client.get(key)
        assert bins["items"] == [1, 2, 3, 4]

    def test_list_append_return_size(self, rust_client, official_client, cleanup):
        """Both clients should return the new list size after append."""
        key = (NS, SET, "la_retsize")
        cleanup.append(key)

        rust_client.put(key, {"items": [10, 20]})

        # Rust client append
        _, _, r_bins = rust_client.operate(key, [rust_lop.list_append("items", 30)])
        # Official client append
        _, _, o_bins = official_client.operate(key, [off_lop.list_append("items", 40)])

        assert r_bins["items"] == 3  # size after first append
        assert o_bins["items"] == 4  # size after second append


# ── List Get by Value Range ────────────────────────────────────────


class TestListGetByValueRange:
    """Compare list_get_by_value_range results across clients."""

    def test_get_by_value_range_same_results(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lgvr")
        cleanup.append(key)

        data = [10, 20, 30, 40, 50]
        rust_client.put(key, {"nums": data})

        # Rust client: get values in range [20, 40)
        rust_ops = [rust_lop.list_get_by_value_range("nums", 20, 40, aerospike_py.LIST_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, rust_ops)

        # Official client: same operation
        off_ops = [off_lop.list_get_by_value_range("nums", aerospike.LIST_RETURN_VALUE, 20, 40)]
        _, _, o_bins = official_client.operate(key, off_ops)

        assert sorted(r_bins["nums"]) == sorted(o_bins["nums"])
        assert sorted(r_bins["nums"]) == [20, 30]

    def test_get_by_value_range_count(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lgvr_cnt")
        cleanup.append(key)

        rust_client.put(key, {"nums": [5, 10, 15, 20, 25]})

        # Return COUNT of items in range [10, 25)
        rust_ops = [rust_lop.list_get_by_value_range("nums", 10, 25, aerospike_py.LIST_RETURN_COUNT)]
        _, _, r_bins = rust_client.operate(key, rust_ops)

        off_ops = [off_lop.list_get_by_value_range("nums", aerospike.LIST_RETURN_COUNT, 10, 25)]
        _, _, o_bins = official_client.operate(key, off_ops)

        assert r_bins["nums"] == o_bins["nums"]
        assert r_bins["nums"] == 3  # 10, 15, 20


# ── List Remove by Value Range (KEY BUG TARGET) ───────────────────


class TestListRemoveByValueRange:
    """KEY BUG TARGET: Verify list_remove_by_value_range argument ordering.

    In operations.rs:449, the call is:
        list_ops::remove_by_value_range(&name, rt, begin, end)
    But get_by_value_range (line 430) uses:
        list_ops::get_by_value_range(&name, begin, end, rt)

    This inconsistency may cause incorrect behavior.
    """

    def test_remove_by_value_range_basic(self, rust_client, official_client, cleanup):
        """Remove values in range [20, 40) and compare remaining list."""
        key_r = (NS, SET, "lrvr_rust")
        key_o = (NS, SET, "lrvr_off")
        cleanup.append(key_r)
        cleanup.append(key_o)

        data = [10, 20, 30, 40, 50]

        # Rust client remove
        rust_client.put(key_r, {"nums": list(data)})
        rust_ops = [rust_lop.list_remove_by_value_range("nums", 20, 40, aerospike_py.LIST_RETURN_VALUE)]
        _, _, r_result = rust_client.operate(key_r, rust_ops)

        # Official client remove
        official_client.put(key_o, {"nums": list(data)})
        off_ops = [off_lop.list_remove_by_value_range("nums", aerospike.LIST_RETURN_VALUE, 20, 40)]
        _, _, o_result = official_client.operate(key_o, off_ops)

        # Removed values should match
        assert sorted(r_result["nums"]) == sorted(o_result["nums"]), (
            f"Bug detected! Rust returned {r_result['nums']}, "
            f"official returned {o_result['nums']}. "
            "Likely arg order issue in operations.rs:449"
        )

        # Remaining list should also match
        _, _, r_remaining = rust_client.get(key_r)
        _, _, o_remaining = official_client.get(key_o)
        assert r_remaining["nums"] == o_remaining["nums"]

    def test_remove_by_value_range_return_count(self, rust_client, official_client, cleanup):
        """Return count of removed items."""
        key_r = (NS, SET, "lrvr_cnt_r")
        key_o = (NS, SET, "lrvr_cnt_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        rust_client.put(key_r, {"nums": list(data)})
        rust_ops = [rust_lop.list_remove_by_value_range("nums", 3, 8, aerospike_py.LIST_RETURN_COUNT)]
        _, _, r_bins = rust_client.operate(key_r, rust_ops)

        official_client.put(key_o, {"nums": list(data)})
        off_ops = [off_lop.list_remove_by_value_range("nums", aerospike.LIST_RETURN_COUNT, 3, 8)]
        _, _, o_bins = official_client.operate(key_o, off_ops)

        assert r_bins["nums"] == o_bins["nums"], f"Count mismatch: rust={r_bins['nums']}, official={o_bins['nums']}"
        assert r_bins["nums"] == 5  # values 3,4,5,6,7

    def test_remove_by_value_range_none_end(self, rust_client, official_client, cleanup):
        """BUG: Remove with unbounded upper - remove all >= begin.

        aerospike-py treats None as Value::Nil (a concrete endpoint),
        resulting in zero removals. The official client treats omitted/None
        end as infinity (unbounded), removing all values >= begin.
        """
        key_r = (NS, SET, "lrvr_none_r")
        key_o = (NS, SET, "lrvr_none_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        data = [10, 20, 30, 40, 50]

        # aerospike-py: None end interpreted as Value::Nil
        rust_client.put(key_r, {"nums": list(data)})
        rust_ops = [rust_lop.list_remove_by_value_range("nums", 30, None, aerospike_py.LIST_RETURN_VALUE)]
        _, _, r_result = rust_client.operate(key_r, rust_ops)

        # Official client: omitted value_end = unbounded (infinity)
        official_client.put(key_o, {"nums": list(data)})
        off_ops = [off_lop.list_remove_by_value_range("nums", aerospike.LIST_RETURN_VALUE, 30)]
        _, _, o_result = official_client.operate(key_o, off_ops)

        # Expected: both remove [30, 40, 50]
        # Actual: rust removes [] (bug), official removes [30, 40, 50]
        assert sorted(r_result["nums"]) == sorted(o_result["nums"]), (
            f"None-end handling mismatch: rust={r_result['nums']}, "
            f"official={o_result['nums']}. "
            "aerospike-py treats None as Nil instead of infinity."
        )

    def test_remove_by_value_range_cross_verify(self, rust_client, official_client, cleanup):
        """Rust removes, official verifies remaining data."""
        key = (NS, SET, "lrvr_cross")
        cleanup.append(key)

        rust_client.put(key, {"nums": [1, 2, 3, 4, 5]})
        rust_ops = [rust_lop.list_remove_by_value_range("nums", 2, 4, aerospike_py.LIST_RETURN_VALUE)]
        rust_client.operate(key, rust_ops)

        _, _, bins = official_client.get(key)
        assert bins["nums"] == [1, 4, 5], f"After removing [2,4), expected [1,4,5] but got {bins['nums']}"


# ── List Remove Operations ─────────────────────────────────────────


class TestListRemoveOperations:
    """Cross-verify list_remove_by_value, by_index, by_rank."""

    def test_remove_by_value_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lrv_cross")
        cleanup.append(key)

        rust_client.put(key, {"items": [10, 20, 30, 20, 40]})
        ops = [rust_lop.list_remove_by_value("items", 20, aerospike_py.LIST_RETURN_COUNT)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["items"] == 2  # two 20s removed

        _, _, remaining = official_client.get(key)
        assert remaining["items"] == [10, 30, 40]

    def test_remove_by_index_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lri_cross")
        cleanup.append(key)

        rust_client.put(key, {"items": ["a", "b", "c", "d"]})
        ops = [rust_lop.list_remove_by_index("items", 1, aerospike_py.LIST_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["items"] == "b"

        _, _, remaining = official_client.get(key)
        assert remaining["items"] == ["a", "c", "d"]

    def test_remove_by_rank_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lrr_cross")
        cleanup.append(key)

        rust_client.put(key, {"items": [30, 10, 50, 20, 40]})
        # rank 0 = smallest value (10)
        ops = [rust_lop.list_remove_by_rank("items", 0, aerospike_py.LIST_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["items"] == 10

        _, _, remaining = official_client.get(key)
        assert 10 not in remaining["items"]


# ── List Increment and Sort ────────────────────────────────────────


class TestListIncrementAndSort:
    """Test list_increment and list_sort compatibility."""

    def test_list_increment_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "linc_cross")
        cleanup.append(key)

        rust_client.put(key, {"nums": [10, 20, 30]})
        ops = [rust_lop.list_increment("nums", 1, 5)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["nums"] == 25  # 20 + 5

        _, _, bins = official_client.get(key)
        assert bins["nums"] == [10, 25, 30]

    def test_list_sort_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "lsort_cross")
        cleanup.append(key)

        rust_client.put(key, {"nums": [50, 10, 30, 20, 40]})
        ops = [rust_lop.list_sort("nums")]
        rust_client.operate(key, ops)

        _, _, bins = official_client.get(key)
        assert bins["nums"] == [10, 20, 30, 40, 50]


# ── Map Put/Get Operations ─────────────────────────────────────────


class TestMapPutGetOperations:
    """Cross-verify map_put, map_get_by_key, map_size."""

    def test_map_put_cross_read(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mp_cross")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1}})
        ops = [rust_mop.map_put("mymap", "b", 2)]
        rust_client.operate(key, ops)

        _, _, bins = official_client.get(key)
        assert bins["mymap"] == {"a": 1, "b": 2}

    def test_map_get_by_key_compare(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mgk_cmp")
        cleanup.append(key)

        data = {"x": 100, "y": 200, "z": 300}
        rust_client.put(key, {"mymap": data})

        # Rust get_by_key
        r_ops = [rust_mop.map_get_by_key("mymap", "y", aerospike_py.MAP_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, r_ops)

        # Official get_by_key
        o_ops = [off_mop.map_get_by_key("mymap", "y", aerospike.MAP_RETURN_VALUE)]
        _, _, o_bins = official_client.operate(key, o_ops)

        assert r_bins["mymap"] == o_bins["mymap"] == 200

    def test_map_size_compare(self, rust_client, official_client, cleanup):
        key = (NS, SET, "ms_cmp")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1, "b": 2, "c": 3}})

        r_ops = [rust_mop.map_size("mymap")]
        _, _, r_bins = rust_client.operate(key, r_ops)

        o_ops = [off_mop.map_size("mymap")]
        _, _, o_bins = official_client.operate(key, o_ops)

        assert r_bins["mymap"] == o_bins["mymap"] == 3

    def test_map_put_items_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mpi_cross")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1}})
        ops = [rust_mop.map_put_items("mymap", {"b": 2, "c": 3})]
        rust_client.operate(key, ops)

        _, _, bins = official_client.get(key)
        assert bins["mymap"] == {"a": 1, "b": 2, "c": 3}


# ── Map Remove Operations ─────────────────────────────────────────


class TestMapRemoveOperations:
    """Cross-verify map_remove_by_key, map_remove_by_value."""

    def test_map_remove_by_key_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mrk_cross")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1, "b": 2, "c": 3}})
        ops = [rust_mop.map_remove_by_key("mymap", "b", aerospike_py.MAP_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["mymap"] == 2

        _, _, remaining = official_client.get(key)
        assert remaining["mymap"] == {"a": 1, "c": 3}

    def test_map_remove_by_value_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mrv_cross")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1, "b": 2, "c": 2, "d": 3}})
        ops = [rust_mop.map_remove_by_value("mymap", 2, aerospike_py.MAP_RETURN_COUNT)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["mymap"] == 2  # "b" and "c" removed

        _, _, remaining = official_client.get(key)
        assert remaining["mymap"] == {"a": 1, "d": 3}

    def test_map_remove_by_key_list_cross(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mrkl_cross")
        cleanup.append(key)

        rust_client.put(key, {"mymap": {"a": 1, "b": 2, "c": 3, "d": 4}})
        ops = [rust_mop.map_remove_by_key_list("mymap", ["a", "c"], aerospike_py.MAP_RETURN_COUNT)]
        _, _, r_bins = rust_client.operate(key, ops)
        assert r_bins["mymap"] == 2

        _, _, remaining = official_client.get(key)
        assert remaining["mymap"] == {"b": 2, "d": 4}


# ── Map Value Range Operations ─────────────────────────────────────


class TestMapValueRangeOperations:
    """Cross-verify map_get/remove_by_value_range."""

    def test_map_get_by_value_range_compare(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mgvr_cmp")
        cleanup.append(key)

        data = {"a": 10, "b": 20, "c": 30, "d": 40, "e": 50}
        rust_client.put(key, {"mymap": data})

        # Range [20, 40)
        r_ops = [rust_mop.map_get_by_value_range("mymap", 20, 40, aerospike_py.MAP_RETURN_KEY)]
        _, _, r_bins = rust_client.operate(key, r_ops)

        # Official: (bin, value_start, value_end, return_type)
        o_ops = [off_mop.map_get_by_value_range("mymap", 20, 40, aerospike.MAP_RETURN_KEY)]
        _, _, o_bins = official_client.operate(key, o_ops)

        assert sorted(r_bins["mymap"]) == sorted(o_bins["mymap"])
        assert sorted(r_bins["mymap"]) == ["b", "c"]

    def test_map_remove_by_value_range_compare(self, rust_client, official_client, cleanup):
        key_r = (NS, SET, "mrvr_r")
        key_o = (NS, SET, "mrvr_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        data = {"a": 10, "b": 20, "c": 30, "d": 40}

        rust_client.put(key_r, {"mymap": dict(data)})
        r_ops = [rust_mop.map_remove_by_value_range("mymap", 20, 40, aerospike_py.MAP_RETURN_KEY)]
        _, _, r_result = rust_client.operate(key_r, r_ops)

        # Official: (bin, value_start, value_end, return_type)
        official_client.put(key_o, {"mymap": dict(data)})
        o_ops = [off_mop.map_remove_by_value_range("mymap", 20, 40, aerospike.MAP_RETURN_KEY)]
        _, _, o_result = official_client.operate(key_o, o_ops)

        assert sorted(r_result["mymap"]) == sorted(o_result["mymap"])

        # Verify remaining data matches
        _, _, r_rem = rust_client.get(key_r)
        _, _, o_rem = official_client.get(key_o)
        assert r_rem["mymap"] == o_rem["mymap"]

    def test_map_get_by_key_range_compare(self, rust_client, official_client, cleanup):
        key = (NS, SET, "mgkr_cmp")
        cleanup.append(key)

        data = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        rust_client.put(key, {"mymap": data})

        # Key range ["b", "d")
        r_ops = [rust_mop.map_get_by_key_range("mymap", "b", "d", aerospike_py.MAP_RETURN_VALUE)]
        _, _, r_bins = rust_client.operate(key, r_ops)

        # Official: (bin, key_range_start, key_range_end, return_type)
        o_ops = [off_mop.map_get_by_key_range("mymap", "b", "d", aerospike.MAP_RETURN_VALUE)]
        _, _, o_bins = official_client.operate(key, o_ops)

        assert sorted(r_bins["mymap"]) == sorted(o_bins["mymap"])
        assert sorted(r_bins["mymap"]) == [2, 3]
