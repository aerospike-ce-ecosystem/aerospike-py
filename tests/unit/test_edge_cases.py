"""Edge case unit tests (no Aerospike server required).

Covers:
- Import smoke tests and __all__ completeness
- list_operations / map_operations dict structure edge cases
- predicates structure edge cases
- exp expression builder edge cases
- NamedTuple unpacking (Record, AerospikeKey, RecordMetadata, etc.)
- Boundary integers and special values
"""

import pytest

import aerospike_py
from aerospike_py import exp, list_operations, map_operations, predicates
from aerospike_py.types import (
    AerospikeKey,
    BinTuple,
    ExistsResult,
    InfoNodeResult,
    OperateOrderedResult,
    Record,
    RecordMetadata,
)

# ═══════════════════════════════════════════════════════════════════
# Import smoke tests
# ═══════════════════════════════════════════════════════════════════


class TestImportSmoke:
    """Verify all public symbols are importable."""

    def test_all_public_symbols_importable(self):
        """Every name in aerospike_py.__all__ is a real attribute."""
        missing = []
        for name in aerospike_py.__all__:
            if not hasattr(aerospike_py, name):
                missing.append(name)
        assert not missing, f"Symbols in __all__ but not importable: {missing}"

    def test_all_completeness(self):
        """Public non-underscore attributes should be in __all__.

        Exceptions: modules, dunder attributes, and stdlib re-imports are excluded.
        """
        import types

        all_set = set(aerospike_py.__all__)
        public_attrs = {
            name
            for name in dir(aerospike_py)
            if not name.startswith("_") and not isinstance(getattr(aerospike_py, name), types.ModuleType)
        }
        # These are known internal names or stdlib re-imports not in __all__
        known_internal = {
            "logger",
            "catch_unexpected",
            # stdlib imports that leak into the namespace
            "Any",
            "PackageNotFoundError",
            "BaseHTTPRequestHandler",
            "HTTPServer",
        }
        public_attrs -= known_internal
        missing_from_all = public_attrs - all_set
        assert not missing_from_all, f"Public attrs not in __all__: {missing_from_all}"

    def test_exp_module_importable(self):
        from aerospike_py import exp as exp_mod

        assert exp_mod is exp

    def test_list_operations_module_importable(self):
        from aerospike_py import list_operations as lo

        assert lo is list_operations

    def test_map_operations_module_importable(self):
        from aerospike_py import map_operations as mo

        assert mo is map_operations

    def test_predicates_module_importable(self):
        from aerospike_py import predicates as p

        assert p is predicates

    def test_exception_module_importable(self):
        from aerospike_py import exception

        assert hasattr(exception, "AerospikeError")

    def test_types_importable(self):
        from aerospike_py.types import AerospikeKey, Record, RecordMetadata

        assert Record is not None
        assert AerospikeKey is not None
        assert RecordMetadata is not None


# ═══════════════════════════════════════════════════════════════════
# NamedTuple unpacking tests
# ═══════════════════════════════════════════════════════════════════


class TestNamedTupleUnpacking:
    """Verify NamedTuple types support correct unpacking and field access."""

    def test_record_unpacking(self):
        key = AerospikeKey("test", "demo", "pk1", b"\x00" * 20)
        meta = RecordMetadata(gen=5, ttl=3600)
        bins = {"name": "Alice", "age": 30}
        record = Record(key=key, meta=meta, bins=bins)

        # Positional unpacking
        k, m, b = record
        assert k is key
        assert m is meta
        assert b is bins

        # Named field access
        assert record.key.namespace == "test"
        assert record.key.set_name == "demo"
        assert record.key.user_key == "pk1"
        assert record.meta.gen == 5
        assert record.meta.ttl == 3600
        assert record.bins["name"] == "Alice"

    def test_record_with_none_fields(self):
        record = Record(key=None, meta=None, bins=None)
        k, m, b = record
        assert k is None
        assert m is None
        assert b is None

    def test_aerospike_key_unpacking(self):
        key = AerospikeKey("ns", "set", 42, b"\xab\xcd")
        ns, set_name, user_key, digest = key
        assert ns == "ns"
        assert set_name == "set"
        assert user_key == 42
        assert digest == b"\xab\xcd"

    def test_aerospike_key_with_bytes_user_key(self):
        key = AerospikeKey("ns", "set", b"\x01\x02", b"\xff" * 20)
        assert key.user_key == b"\x01\x02"
        assert isinstance(key.user_key, bytes)

    def test_aerospike_key_with_none_user_key(self):
        key = AerospikeKey("ns", "set", None, b"\x00" * 20)
        assert key.user_key is None

    def test_record_metadata_unpacking(self):
        meta = RecordMetadata(gen=1, ttl=0)
        gen, ttl = meta
        assert gen == 1
        assert ttl == 0

    def test_exists_result_unpacking(self):
        key = AerospikeKey("ns", "set", "pk", b"\x00" * 20)
        meta = RecordMetadata(gen=3, ttl=100)
        result = ExistsResult(key=key, meta=meta)
        k, m = result
        assert k is key
        assert m is meta

    def test_exists_result_none_meta(self):
        """Exists result with None meta means record not found."""
        result = ExistsResult(key=None, meta=None)
        assert result.meta is None

    def test_info_node_result_unpacking(self):
        result = InfoNodeResult(node_name="BB9010", error_code=0, response="build=7.0.0")
        name, code, resp = result
        assert name == "BB9010"
        assert code == 0
        assert resp == "build=7.0.0"

    def test_bin_tuple_unpacking(self):
        bt = BinTuple(name="counter", value=42)
        n, v = bt
        assert n == "counter"
        assert v == 42

    def test_operate_ordered_result_unpacking(self):
        key = AerospikeKey("ns", "set", "pk", b"\x00" * 20)
        meta = RecordMetadata(gen=2, ttl=500)
        bins = [BinTuple("a", 1), BinTuple("b", "hello")]
        result = OperateOrderedResult(key=key, meta=meta, ordered_bins=bins)
        k, m, ob = result
        assert k is key
        assert m is meta
        assert len(ob) == 2
        assert ob[0].name == "a"
        assert ob[1].value == "hello"


# ═══════════════════════════════════════════════════════════════════
# list_operations edge cases
# ═══════════════════════════════════════════════════════════════════


class TestListOperationsEdgeCases:
    """Edge case tests for list operation helper functions."""

    def test_list_append_none_value(self):
        """Appending None should be a valid operation."""
        op = list_operations.list_append("bin", None)
        assert op["op"] == 1001
        assert op["val"] is None

    def test_list_append_empty_bin_name(self):
        """Empty bin name should still produce a valid operation dict."""
        op = list_operations.list_append("", 42)
        assert op["bin"] == ""
        assert op["val"] == 42

    def test_list_append_nested_list(self):
        """Appending a nested list should preserve structure."""
        nested = [[1, 2], [3, 4]]
        op = list_operations.list_append("bin", nested)
        assert op["val"] == [[1, 2], [3, 4]]

    def test_list_insert_negative_index(self):
        """Negative index should be accepted (server interprets it)."""
        op = list_operations.list_insert("bin", -1, "val")
        assert op["index"] == -1

    def test_list_pop_zero_index(self):
        op = list_operations.list_pop("bin", 0)
        assert op["index"] == 0

    def test_list_get_range_zero_count(self):
        op = list_operations.list_get_range("bin", 0, 0)
        assert op["count"] == 0

    def test_list_set_order(self):
        op = list_operations.list_set_order("bin", 1)
        assert op["op"] == 1031
        assert op["val"] == 1

    @pytest.mark.parametrize(
        "func_name",
        [name for name in list_operations.__all__ if name != "Operation"],
    )
    def test_all_list_operations_are_callable(self, func_name):
        """Every exported list operation function is callable."""
        func = getattr(list_operations, func_name)
        assert callable(func)

    def test_list_operations_all_return_dict(self):
        """Verify a sample of list operations all return dicts with 'op' and 'bin' keys."""
        ops = [
            list_operations.list_append("b", 1),
            list_operations.list_clear("b"),
            list_operations.list_size("b"),
            list_operations.list_get("b", 0),
            list_operations.list_sort("b"),
        ]
        for op in ops:
            assert isinstance(op, dict)
            assert "op" in op
            assert "bin" in op


# ═══════════════════════════════════════════════════════════════════
# map_operations edge cases
# ═══════════════════════════════════════════════════════════════════


class TestMapOperationsEdgeCases:
    """Edge case tests for map operation helper functions."""

    def test_map_put_none_value(self):
        op = map_operations.map_put("bin", "key", None)
        assert op["val"] is None

    def test_map_put_empty_key(self):
        op = map_operations.map_put("bin", "", "val")
        assert op["map_key"] == ""

    def test_map_put_items_empty_dict(self):
        op = map_operations.map_put_items("bin", {})
        assert op["val"] == {}

    def test_map_put_integer_key(self):
        """Map keys can be integers."""
        op = map_operations.map_put("bin", 42, "value")
        assert op["map_key"] == 42

    def test_map_set_order(self):
        op = map_operations.map_set_order("bin", 1)
        assert op["op"] == 2001
        assert op["val"] == 1

    @pytest.mark.parametrize(
        "func_name",
        [name for name in map_operations.__all__ if name != "Operation"],
    )
    def test_all_map_operations_are_callable(self, func_name):
        """Every exported map operation function is callable."""
        func = getattr(map_operations, func_name)
        assert callable(func)

    def test_map_operations_all_return_dict(self):
        """Verify a sample of map operations all return dicts with 'op' and 'bin' keys."""
        ops = [
            map_operations.map_put("b", "k", "v"),
            map_operations.map_clear("b"),
            map_operations.map_size("b"),
            map_operations.map_get_by_key("b", "k", 7),
            map_operations.map_set_order("b", 0),
        ]
        for op in ops:
            assert isinstance(op, dict)
            assert "op" in op
            assert "bin" in op


# ═══════════════════════════════════════════════════════════════════
# Expression builder edge cases
# ═══════════════════════════════════════════════════════════════════


class TestExpEdgeCases:
    """Edge case tests for expression builders."""

    def test_empty_string_bin_name(self):
        e = exp.int_bin("")
        assert e["name"] == ""

    def test_int_val_zero(self):
        e = exp.int_val(0)
        assert e["val"] == 0

    def test_int_val_max_64bit(self):
        e = exp.int_val(2**63 - 1)
        assert e["val"] == 2**63 - 1

    def test_int_val_min_64bit(self):
        e = exp.int_val(-(2**63))
        assert e["val"] == -(2**63)

    def test_float_val_negative_zero(self):
        e = exp.float_val(-0.0)
        assert e["val"] == -0.0

    def test_float_val_inf(self):
        e = exp.float_val(float("inf"))
        assert e["val"] == float("inf")

    def test_float_val_nan(self):
        import math

        e = exp.float_val(float("nan"))
        assert math.isnan(e["val"])

    def test_string_val_unicode(self):
        e = exp.string_val("unicode test")
        assert e["val"] == "unicode test"

    def test_blob_val_empty(self):
        e = exp.blob_val(b"")
        assert e["val"] == b""

    def test_list_val_nested(self):
        nested = [[1, [2, 3]], {"a": 1}]
        e = exp.list_val(nested)
        assert e["val"] == nested

    def test_map_val_nested(self):
        nested = {"a": {"b": [1, 2, 3]}}
        e = exp.map_val(nested)
        assert e["val"] == nested

    def test_cond_single_default(self):
        """cond with a single expression (just the default) should still work."""
        e = exp.cond(exp.string_val("default"))
        assert e["__expr__"] == "cond"
        assert len(e["exprs"]) == 1

    def test_and_single_operand(self):
        """and_ with a single operand should still produce a valid dict."""
        e = exp.and_(exp.bool_val(True))
        assert e["__expr__"] == "and"
        assert len(e["exprs"]) == 1

    def test_or_single_operand(self):
        e = exp.or_(exp.bool_val(False))
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 1

    def test_expression_dict_is_plain_dict(self):
        """Expression nodes are plain dicts, not special classes."""
        e = exp.int_val(42)
        assert type(e) is dict

    def test_min_max_builders(self):
        e_min = exp.min_(exp.int_bin("a"), exp.int_bin("b"))
        e_max = exp.max_(exp.int_bin("a"), exp.int_bin("b"))
        assert e_min["__expr__"] == "min"
        assert e_max["__expr__"] == "max"
        assert len(e_min["exprs"]) == 2
        assert len(e_max["exprs"]) == 2


# ═══════════════════════════════════════════════════════════════════
# Predicates edge cases
# ═══════════════════════════════════════════════════════════════════


class TestPredicateEdgeCases:
    def test_equals_none_value(self):
        """equals() with None value should produce a valid tuple."""
        result = predicates.equals("bin", None)
        assert result == ("equals", "bin", None)

    def test_equals_empty_bin_name(self):
        result = predicates.equals("", 42)
        assert result[1] == ""

    def test_between_same_values(self):
        """between(bin, x, x) should be valid (degenerate range)."""
        result = predicates.between("bin", 10, 10)
        assert result == ("between", "bin", 10, 10)

    def test_contains_with_none_value(self):
        from aerospike_py import INDEX_TYPE_LIST

        result = predicates.contains("bin", INDEX_TYPE_LIST, None)
        assert result == ("contains", "bin", INDEX_TYPE_LIST, None)


# ═══════════════════════════════════════════════════════════════════
# Client factory edge cases
# ═══════════════════════════════════════════════════════════════════


class TestClientFactoryEdgeCases:
    def test_client_with_empty_hosts(self):
        """Client creation with empty hosts list should succeed (fails on connect)."""
        c = aerospike_py.client({"hosts": []})
        assert not c.is_connected()

    def test_client_with_multiple_hosts(self):
        c = aerospike_py.client({"hosts": [("host1", 3000), ("host2", 3001)]})
        assert isinstance(c, aerospike_py.Client)

    def test_client_is_instance_of_native(self):
        """Client should be a subclass of the native client."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        assert isinstance(c, aerospike_py.Client)

    def test_async_client_creation(self):
        c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
        assert not c.is_connected()

    def test_async_client_is_correct_type(self):
        c = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
        assert isinstance(c, aerospike_py.AsyncClient)


# ═══════════════════════════════════════════════════════════════════
# Boundary integer tests
# ═══════════════════════════════════════════════════════════════════


class TestBoundaryIntegers:
    """Test boundary integer values in various contexts."""

    @pytest.mark.parametrize(
        "value",
        [0, 1, -1, 2**31 - 1, -(2**31), 2**63 - 1, -(2**63)],
        ids=["zero", "one", "neg_one", "max_i32", "min_i32", "max_i64", "min_i64"],
    )
    def test_exp_int_val_boundary(self, value):
        """int_val accepts boundary integers."""
        e = exp.int_val(value)
        assert e["val"] == value

    @pytest.mark.parametrize(
        "value",
        [0, 1, -1, 2**31 - 1, -(2**31)],
        ids=["zero", "one", "neg_one", "max_i32", "min_i32"],
    )
    def test_predicate_equals_boundary(self, value):
        """equals() accepts boundary integer values."""
        result = predicates.equals("bin", value)
        assert result[2] == value

    @pytest.mark.parametrize(
        "gen,ttl",
        [(0, 0), (1, 1), (2**32 - 1, 2**32 - 1), (0, 2**31 - 1)],
        ids=["zeros", "ones", "max_u32", "mixed"],
    )
    def test_record_metadata_boundary(self, gen, ttl):
        """RecordMetadata handles boundary generation and TTL values."""
        meta = RecordMetadata(gen=gen, ttl=ttl)
        assert meta.gen == gen
        assert meta.ttl == ttl
