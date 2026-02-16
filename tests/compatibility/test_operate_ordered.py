"""operate_ordered compatibility tests.

Verifies that operate_ordered returns correctly ordered results as
a list of (bin_name, value) tuples, matching the official client's behavior.

Key concern: operations.rs uses HashMap iteration for bins (line 808-818),
which may not preserve operation ordering.
"""

import pytest

import aerospike_py
from aerospike_py import list_operations as rust_lop
from aerospike_py import map_operations as rust_mop

aerospike = pytest.importorskip("aerospike")
from aerospike_helpers.operations import list_operations as off_lop  # noqa: E402
from aerospike_helpers.operations import map_operations as off_mop  # noqa: E402
from aerospike_helpers.operations import operations as off_ops  # noqa: E402

NS = "test"
SET = "compat_oo"

# Upstream aerospike-client-rust uses HashMap for Record.bins,
# which loses insertion order and collapses duplicate keys.
# See: https://github.com/aerospike/aerospike-client-rust/issues/183
#      https://github.com/aerospike/aerospike-client-rust/pull/184
_SKIP_UPSTREAM = "upstream aerospike-client-rust HashMap bin ordering issue (aerospike-client-rust#183)"


class TestOperateOrderedBinOrdering:
    """Verify that READ operations return in the correct order."""

    @pytest.mark.skip(reason=_SKIP_UPSTREAM)
    def test_multiple_reads_preserve_order(self, rust_client, official_client, cleanup):
        """Multiple READ ops should return in operation order."""
        key = (NS, SET, "oo_read_order")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})

        # Read bins in a specific order
        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "e", "val": ""},
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": ""},
            {"op": aerospike_py.OPERATOR_READ, "bin": "c", "val": ""},
            {"op": aerospike_py.OPERATOR_READ, "bin": "b", "val": ""},
            {"op": aerospike_py.OPERATOR_READ, "bin": "d", "val": ""},
        ]
        _, _, r_ordered = rust_client.operate_ordered(key, ops)

        off_op_list = [
            off_ops.read("e"),
            off_ops.read("a"),
            off_ops.read("c"),
            off_ops.read("b"),
            off_ops.read("d"),
        ]
        _, _, o_ordered = official_client.operate_ordered(key, off_op_list)

        # Both should return list of (name, value) tuples in the same order
        assert isinstance(r_ordered, list)
        assert isinstance(o_ordered, list)

        r_names = [name for name, _ in r_ordered]
        o_names = [name for name, _ in o_ordered]
        assert r_names == o_names, f"Ordering mismatch: rust={r_names}, official={o_names}"

        r_values = [val for _, val in r_ordered]
        o_values = [val for _, val in o_ordered]
        assert r_values == o_values

    @pytest.mark.skip(reason=_SKIP_UPSTREAM)
    def test_same_bin_multiple_reads(self, rust_client, official_client, cleanup):
        """BUG: Reading the same bin multiple times should appear as separate entries.

        Rust client collapses same-bin results:
        - Rust: [('counter', [100, 101])] - collapsed to 1 entry with list
        - Official: [('counter', 100), ('counter', 101)] - 2 separate entries
        """
        key_r = (NS, SET, "oo_same_bin_r")
        key_o = (NS, SET, "oo_same_bin_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        rust_client.put(key_r, {"counter": 100})
        official_client.put(key_o, {"counter": 100})

        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": ""},
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": ""},
        ]
        _, _, r_ordered = rust_client.operate_ordered(key_r, ops)

        off_op_list = [
            off_ops.read("counter"),
            off_ops.increment("counter", 1),
            off_ops.read("counter"),
        ]
        _, _, o_ordered = official_client.operate_ordered(key_o, off_op_list)

        # Official returns separate entries for each read
        assert len(r_ordered) == len(o_ordered), (
            f"Entry count mismatch: rust={r_ordered}, official={o_ordered}. "
            "Rust collapses same-bin entries into a single list."
        )


class TestOperateOrderedMixedOps:
    """INCR + APPEND + READ mixed operations."""

    def test_incr_append_read_mixed(self, rust_client, official_client, cleanup):
        """BUG: Mixed INCR/APPEND/READ operations in operate_ordered.

        Note: This test uses separate keys to avoid data contamination.
        """
        key_r = (NS, SET, "oo_mixed_r")
        key_o = (NS, SET, "oo_mixed_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        rust_client.put(key_r, {"count": 10, "name": "hello"})
        official_client.put(key_o, {"count": 10, "name": "hello"})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "count", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "count", "val": ""},
            {"op": aerospike_py.OPERATOR_APPEND, "bin": "name", "val": " world"},
            {"op": aerospike_py.OPERATOR_READ, "bin": "name", "val": ""},
        ]
        _, _, r_ordered = rust_client.operate_ordered(key_r, ops)

        off_op_list = [
            off_ops.increment("count", 5),
            off_ops.read("count"),
            off_ops.append("name", " world"),
            off_ops.read("name"),
        ]
        _, _, o_ordered = official_client.operate_ordered(key_o, off_op_list)

        # Both should return the same values for the reads
        r_dict = dict(r_ordered)
        o_dict = dict(o_ordered)

        assert r_dict.get("count") == o_dict.get("count"), (
            f"count mismatch: rust={r_dict.get('count')}, official={o_dict.get('count')}"
        )
        assert r_dict.get("name") == o_dict.get("name"), (
            f"name mismatch: rust={r_dict.get('name')}, official={o_dict.get('name')}"
        )


class TestOperateOrderedReturnTypes:
    """Verify return type structure: (key, meta, list[tuple[str, Any]])."""

    def test_return_structure(self, rust_client, cleanup):
        key = (NS, SET, "oo_struct")
        cleanup.append(key)

        rust_client.put(key, {"val": 42})

        ops = [{"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": ""}]
        result = rust_client.operate_ordered(key, ops)

        assert isinstance(result, tuple)
        assert len(result) == 3

        key_part, meta_part, ordered_part = result

        # Key should be a tuple
        assert isinstance(key_part, tuple)

        # Meta should be a dict with gen and ttl
        assert isinstance(meta_part, dict)
        assert "gen" in meta_part
        assert "ttl" in meta_part

        # Ordered bins should be a list of tuples
        assert isinstance(ordered_part, list)
        for item in ordered_part:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)

    @pytest.mark.skip(reason=_SKIP_UPSTREAM)
    def test_return_structure_matches_official(self, rust_client, official_client, cleanup):
        """Both clients should return the same structure."""
        key = (NS, SET, "oo_struct_cmp")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": "hello"})

        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "a", "val": ""},
            {"op": aerospike_py.OPERATOR_READ, "bin": "b", "val": ""},
        ]
        r_key, r_meta, r_ordered = rust_client.operate_ordered(key, ops)

        off_op_list = [off_ops.read("a"), off_ops.read("b")]
        o_key, o_meta, o_ordered = official_client.operate_ordered(key, off_op_list)

        # Meta generation should match
        assert r_meta["gen"] == o_meta["gen"]

        # Ordered bins content should match
        assert r_ordered == o_ordered


class TestOperateOrderedWithCDT:
    """CDT operations within operate_ordered."""

    @pytest.mark.skip(reason=_SKIP_UPSTREAM)
    def test_list_ops_in_ordered(self, rust_client, official_client, cleanup):
        """BUG: CDT list operations same-bin results should be separate entries.

        Rust client collapses same-bin results into a single entry with
        a list value: [('items', [4, 4])] instead of expected
        [('items', 4), ('items', 4)].
        """
        key_r = (NS, SET, "oo_cdt_list_r")
        key_o = (NS, SET, "oo_cdt_list_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        rust_client.put(key_r, {"items": [10, 20, 30]})
        official_client.put(key_o, {"items": [10, 20, 30]})

        ops = [
            rust_lop.list_append("items", 40),
            rust_lop.list_size("items"),
        ]
        _, _, r_ordered = rust_client.operate_ordered(key_r, ops)

        off_op_list = [
            off_lop.list_append("items", 40),
            off_lop.list_size("items"),
        ]
        _, _, o_ordered = official_client.operate_ordered(key_o, off_op_list)

        # Official: [('items', 4), ('items', 4)] - two separate entries
        # Rust bug: [('items', [4, 4])] - collapsed into one
        assert len(r_ordered) == len(o_ordered), (
            f"Entry count mismatch: rust={r_ordered}, official={o_ordered}. Rust collapses same-bin results."
        )

    @pytest.mark.skip(reason=_SKIP_UPSTREAM)
    def test_map_ops_in_ordered(self, rust_client, official_client, cleanup):
        """BUG: CDT map operations same-bin results should be separate entries."""
        key_r = (NS, SET, "oo_cdt_map_r")
        key_o = (NS, SET, "oo_cdt_map_o")
        cleanup.append(key_r)
        cleanup.append(key_o)

        rust_client.put(key_r, {"mymap": {"a": 1, "b": 2}})
        official_client.put(key_o, {"mymap": {"a": 1, "b": 2}})

        ops = [
            rust_mop.map_put("mymap", "c", 3),
            rust_mop.map_size("mymap"),
        ]
        _, _, r_ordered = rust_client.operate_ordered(key_r, ops)

        off_op_list = [
            off_mop.map_put("mymap", "c", 3),
            off_mop.map_size("mymap"),
        ]
        _, _, o_ordered = official_client.operate_ordered(key_o, off_op_list)

        # Official: [('mymap', 3), ('mymap', 3)] - separate entries
        # Rust bug: [('mymap', [3, 3])] - collapsed
        assert len(r_ordered) == len(o_ordered), (
            f"Entry count mismatch: rust={r_ordered}, official={o_ordered}. Rust collapses same-bin results."
        )
