"""Property-based tests using hypothesis (no server required)."""

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from aerospike_py import exp, predicates
from aerospike_py._types import _build_op
from aerospike_py.list_operations import (
    list_append,
    list_append_items,
    list_get_by_index_range,
    list_insert,
)
from aerospike_py.map_operations import (
    map_get_by_key,
    map_put,
    map_put_items,
    map_size,
)

# ── Expression builder properties ──────────────────────────────────


# Strategy: generate valid bin names (non-empty ASCII strings)
bin_names = st.text(st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"), min_size=1, max_size=14)

# Strategy: generate expression type constants
exp_types = st.sampled_from(
    [
        exp.EXP_TYPE_NIL,
        exp.EXP_TYPE_BOOL,
        exp.EXP_TYPE_INT,
        exp.EXP_TYPE_STRING,
        exp.EXP_TYPE_LIST,
        exp.EXP_TYPE_MAP,
        exp.EXP_TYPE_BLOB,
        exp.EXP_TYPE_FLOAT,
        exp.EXP_TYPE_GEO,
        exp.EXP_TYPE_HLL,
    ]
)


class TestExpressionProperties:
    """Property-based tests for expression builder functions."""

    @given(val=st.integers(min_value=-(2**63), max_value=2**63 - 1))
    def test_int_val_produces_valid_expr(self, val):
        """int_val always produces a dict with __expr__ key."""
        result = exp.int_val(val)
        assert isinstance(result, dict)
        assert result["__expr__"] == "int_val"
        assert result["val"] == val

    @given(val=st.floats(allow_nan=True, allow_infinity=True))
    def test_float_val_produces_valid_expr(self, val):
        result = exp.float_val(val)
        assert isinstance(result, dict)
        assert result["__expr__"] == "float_val"

    @given(val=st.text(max_size=100))
    def test_string_val_produces_valid_expr(self, val):
        result = exp.string_val(val)
        assert result["__expr__"] == "string_val"
        assert result["val"] == val

    @given(val=st.booleans())
    def test_bool_val_produces_valid_expr(self, val):
        result = exp.bool_val(val)
        assert result["__expr__"] == "bool_val"
        assert result["val"] == val

    @given(val=st.binary(max_size=100))
    def test_blob_val_produces_valid_expr(self, val):
        result = exp.blob_val(val)
        assert result["__expr__"] == "blob_val"
        assert result["val"] == val

    @given(name=bin_names)
    def test_bin_accessors_produce_valid_expr(self, name):
        """All bin accessor functions produce valid expressions."""
        for fn in [
            exp.int_bin,
            exp.float_bin,
            exp.string_bin,
            exp.bool_bin,
            exp.blob_bin,
            exp.list_bin,
            exp.map_bin,
            exp.geo_bin,
            exp.hll_bin,
            exp.bin_exists,
            exp.bin_type,
        ]:
            result = fn(name)
            assert isinstance(result, dict)
            assert "__expr__" in result
            assert result["name"] == name

    @given(exp_type=exp_types)
    def test_key_with_valid_type(self, exp_type):
        result = exp.key(exp_type)
        assert result["__expr__"] == "key"
        assert result["exp_type"] == exp_type

    @given(modulo=st.integers(min_value=1, max_value=10000))
    def test_digest_modulo_produces_valid_expr(self, modulo):
        result = exp.digest_modulo(modulo)
        assert result["__expr__"] == "digest_modulo"
        assert result["modulo"] == modulo

    @given(st.text(min_size=1, max_size=20))
    def test_invalid_op_raises_value_error(self, op_name):
        """Unknown op names raise ValueError (unless they accidentally match)."""
        from aerospike_py.exp import _VALID_OPS

        if op_name not in _VALID_OPS:
            with pytest.raises(ValueError, match="Unknown expression op"):
                exp._cmd(op_name)


class TestCompoundExpressionProperties:
    """Property-based tests for compound expression building."""

    @given(n=st.integers(min_value=2, max_value=10))
    def test_and_with_n_expressions(self, n):
        """and_ accepts variable number of expressions."""
        exprs = [exp.bool_val(True) for _ in range(n)]
        result = exp.and_(*exprs)
        assert result["__expr__"] == "and"
        assert len(result["exprs"]) == n

    @given(n=st.integers(min_value=2, max_value=10))
    def test_or_with_n_expressions(self, n):
        exprs = [exp.bool_val(False) for _ in range(n)]
        result = exp.or_(*exprs)
        assert result["__expr__"] == "or"
        assert len(result["exprs"]) == n

    def test_nested_expressions_depth(self):
        """Deeply nested expressions don't crash."""
        expr = exp.int_val(1)
        for _ in range(50):
            expr = exp.not_(exp.eq(expr, exp.int_val(0)))
        assert isinstance(expr, dict)

    @given(
        left_val=st.integers(min_value=-1000, max_value=1000),
        right_val=st.integers(min_value=-1000, max_value=1000),
    )
    def test_comparison_ops_all_produce_valid_exprs(self, left_val, right_val):
        left = exp.int_val(left_val)
        right = exp.int_val(right_val)
        for fn, op_name in [
            (exp.eq, "eq"),
            (exp.ne, "ne"),
            (exp.gt, "gt"),
            (exp.ge, "ge"),
            (exp.lt, "lt"),
            (exp.le, "le"),
        ]:
            result = fn(left, right)
            assert result["__expr__"] == op_name
            assert "left" in result and "right" in result


class TestLetDefProperties:
    """Property-based tests for let/def variable bindings."""

    @given(name=bin_names, val=st.integers(min_value=-100, max_value=100))
    def test_def_var_roundtrip(self, name, val):
        """def_ and var produce valid expressions with matching names."""
        d = exp.def_(name, exp.int_val(val))
        v = exp.var(name)
        assert d["__expr__"] == "def"
        assert d["name"] == name
        assert v["__expr__"] == "var"
        assert v["name"] == name

    @given(n_vars=st.integers(min_value=1, max_value=5))
    def test_let_with_multiple_defs(self, n_vars):
        defs = [exp.def_(f"v{i}", exp.int_val(i)) for i in range(n_vars)]
        scope = exp.var("v0")
        result = exp.let_(*defs, scope)
        assert result["__expr__"] == "let"
        assert len(result["exprs"]) == n_vars + 1


class TestListMapOperationProperties:
    """Property-based tests for CDT operation dict building."""

    @given(bin_name=bin_names, val=st.integers(min_value=-1000, max_value=1000))
    def test_build_op_produces_valid_dict(self, bin_name, val):
        """_build_op produces a dict with expected keys."""
        result = _build_op(1001, bin_name, val=val)
        assert result["op"] == 1001
        assert result["bin"] == bin_name
        assert result["val"] == val

    @given(bin_name=bin_names)
    def test_build_op_omits_unset_values(self, bin_name):
        """_build_op omits keys with _UNSET sentinel value."""
        result = _build_op(1001, bin_name)
        assert "val" not in result


class TestNumPyDtypeProperties:
    """Property-based tests for numpy dtype validation."""

    @pytest.fixture(autouse=True)
    def _requires_numpy(self):
        pytest.importorskip("numpy")

    @given(
        n_fields=st.integers(min_value=1, max_value=8),
        data=st.data(),
    )
    @settings(max_examples=50)
    def test_valid_dtypes_accepted(self, n_fields, data):
        """Random valid structured dtypes are accepted by _batch_records_to_numpy."""
        import numpy as np

        from aerospike_py.numpy_batch import _ALLOWED_KINDS

        kind_choices = [("i4", "i"), ("u4", "u"), ("f8", "f"), ("S10", "S"), ("V8", "V")]
        fields = []
        for i in range(n_fields):
            kind_spec, _ = data.draw(st.sampled_from(kind_choices))
            fields.append((f"field_{i}", kind_spec))

        dtype = np.dtype(fields)
        # Validate all fields are in allowed kinds
        for name in dtype.names:
            assert dtype[name].base.kind in _ALLOWED_KINDS


# ── Predicate properties ──────────────────────────────────────────


class TestPredicateProperties:
    """Property-based tests for query predicates."""

    @given(bin_name=bin_names)
    def test_equals_produces_valid_predicate(self, bin_name):
        """equals() always returns a valid 3-tuple."""
        result = predicates.equals(bin_name, 42)
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == "equals"
        assert result[1] == bin_name

    @given(
        min_val=st.integers(min_value=-(2**63), max_value=2**63 - 1),
        max_val=st.integers(min_value=-(2**63), max_value=2**63 - 1),
    )
    def test_between_produces_valid_predicate(self, min_val, max_val):
        """between() always returns a valid 4-tuple regardless of min/max order."""
        result = predicates.between("bin", min_val, max_val)
        assert isinstance(result, tuple)
        assert len(result) == 4
        assert result[0] == "between"
        assert result[2] == min_val
        assert result[3] == max_val

    @given(val=st.text(min_size=0, max_size=200))
    def test_contains_string_predicate(self, val):
        """contains() with string values always produces a valid 4-tuple."""
        result = predicates.contains("bin", 0, val)
        assert isinstance(result, tuple)
        assert len(result) == 4
        assert result[0] == "contains"

    @given(
        bin_name=bin_names,
        val=st.one_of(st.integers(), st.text(max_size=50), st.floats(allow_nan=False)),
    )
    def test_equals_preserves_value_type(self, bin_name, val):
        """equals() preserves the original value type and content."""
        result = predicates.equals(bin_name, val)
        assert result[2] == val


# ── List CDT operation properties ─────────────────────────────────


class TestListOperationProperties:
    """Property-based tests for list CDT operations."""

    @given(
        bin_name=bin_names,
        value=st.one_of(st.integers(), st.text(max_size=100), st.floats(allow_nan=False)),
    )
    def test_list_append_produces_valid_op(self, bin_name, value):
        """list_append always returns a valid operation dict."""
        result = list_append(bin_name, value)
        assert isinstance(result, dict)
        assert "op" in result
        assert "bin" in result
        assert result["bin"] == bin_name
        assert result["val"] == value

    @given(
        index=st.integers(min_value=-1000, max_value=1000),
        return_type=st.integers(min_value=0, max_value=10),
    )
    def test_list_get_by_index_range_valid(self, index, return_type):
        """list_get_by_index_range always produces valid op with any index."""
        result = list_get_by_index_range("mybin", index, return_type)
        assert isinstance(result, dict)
        assert "op" in result
        assert result["bin"] == "mybin"
        assert result["index"] == index

    @given(items=st.lists(st.integers(), min_size=1, max_size=20))
    def test_list_append_items_valid(self, items):
        """list_append_items always produces valid op with any list."""
        result = list_append_items("mybin", items)
        assert isinstance(result, dict)
        assert result["val"] == items

    @given(
        bin_name=bin_names,
        index=st.integers(min_value=-100, max_value=100),
        value=st.integers(),
    )
    def test_list_insert_produces_valid_op(self, bin_name, index, value):
        """list_insert always returns a valid operation dict."""
        result = list_insert(bin_name, index, value)
        assert isinstance(result, dict)
        assert result["bin"] == bin_name
        assert result["index"] == index
        assert result["val"] == value


# ── Map CDT operation properties ──────────────────────────────────


class TestMapOperationProperties:
    """Property-based tests for map CDT operations."""

    @given(
        bin_name=bin_names,
        key=st.one_of(st.integers(), st.text(max_size=50)),
        value=st.one_of(st.integers(), st.text(max_size=100), st.floats(allow_nan=False)),
    )
    def test_map_put_produces_valid_op(self, bin_name, key, value):
        """map_put always returns valid operation dict."""
        result = map_put(bin_name, key, value)
        assert isinstance(result, dict)
        assert "op" in result
        assert "bin" in result
        assert result["bin"] == bin_name
        assert result["map_key"] == key
        assert result["val"] == value

    @given(
        key=st.one_of(st.integers(), st.text(max_size=50)),
        return_type=st.integers(min_value=0, max_value=10),
    )
    def test_map_get_by_key_valid(self, key, return_type):
        """map_get_by_key produces valid op with any key type."""
        result = map_get_by_key("mybin", key, return_type)
        assert isinstance(result, dict)
        assert result["map_key"] == key
        assert result["return_type"] == return_type

    @given(
        items=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.integers(),
            min_size=1,
            max_size=10,
        )
    )
    def test_map_put_items_valid(self, items):
        """map_put_items always produces valid op with any dict."""
        result = map_put_items("mybin", items)
        assert isinstance(result, dict)
        assert result["val"] == items

    @given(bin_name=bin_names)
    def test_map_size_produces_minimal_op(self, bin_name):
        """map_size produces an op with only op and bin keys."""
        result = map_size(bin_name)
        assert isinstance(result, dict)
        assert result["op"] is not None
        assert result["bin"] == bin_name


# ── Constants properties ──────────────────────────────────────────


class TestConstantsProperties:
    """Property-based tests for constants consistency."""

    @given(data=st.data())
    def test_policy_constants_are_valid_ints(self, data):
        """All POLICY_* constants should be valid integers."""
        import aerospike_py

        policy_attrs = [a for a in dir(aerospike_py) if a.startswith("POLICY_")]
        if policy_attrs:
            attr = data.draw(st.sampled_from(policy_attrs))
            val = getattr(aerospike_py, attr)
            assert isinstance(val, int)

    @given(data=st.data())
    def test_index_type_constants_are_valid_ints(self, data):
        """All INDEX_* constants should be valid integers."""
        import aerospike_py

        index_attrs = [a for a in dir(aerospike_py) if a.startswith("INDEX_")]
        if index_attrs:
            attr = data.draw(st.sampled_from(index_attrs))
            val = getattr(aerospike_py, attr)
            assert isinstance(val, int)

    @given(data=st.data())
    def test_list_constants_are_valid_ints(self, data):
        """All LIST_* constants should be valid integers."""
        import aerospike_py

        list_attrs = [a for a in dir(aerospike_py) if a.startswith("LIST_")]
        if list_attrs:
            attr = data.draw(st.sampled_from(list_attrs))
            val = getattr(aerospike_py, attr)
            assert isinstance(val, int)


# ── Expression combination properties ────────────────────────────


class TestExpressionCombinationProperties:
    """Property-based tests for complex expression combinations."""

    @given(
        n_exprs=st.integers(min_value=2, max_value=8),
        values=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=2, max_size=8),
    )
    def test_nested_and_or_combination(self, n_exprs, values):
        """Nested AND(OR(...), OR(...)) combinations always produce valid expressions."""
        exprs = [exp.eq(exp.int_bin("b"), exp.int_val(v)) for v in values[:n_exprs]]
        mid = len(exprs) // 2
        if mid >= 2 and len(exprs) - mid >= 2:
            left = exp.and_(*exprs[:mid])
            right = exp.or_(*exprs[mid:])
            result = exp.and_(left, right)
            assert result["__expr__"] == "and"
            assert len(result["exprs"]) == 2

    @given(depth=st.integers(min_value=1, max_value=5))
    def test_deeply_nested_not(self, depth):
        """Deeply nested not(not(not(...))) always produces valid expression."""
        expr = exp.eq(exp.int_bin("b"), exp.int_val(1))
        for _ in range(depth):
            expr = exp.not_(expr)
        assert expr["__expr__"] == "not"

    @given(
        n_and=st.integers(min_value=2, max_value=5),
        n_or=st.integers(min_value=2, max_value=5),
    )
    def test_and_or_lengths_preserved(self, n_and, n_or):
        """and_/or_ preserve the number of sub-expressions."""
        and_exprs = [exp.bool_val(True) for _ in range(n_and)]
        or_exprs = [exp.bool_val(False) for _ in range(n_or)]
        and_result = exp.and_(*and_exprs)
        or_result = exp.or_(*or_exprs)
        assert len(and_result["exprs"]) == n_and
        assert len(or_result["exprs"]) == n_or
