"""Unit tests for expression filter builder (no server required)."""

import pytest

from aerospike_py import exp

# ── Parametrized value constructor tests ────────────────────────────────


@pytest.mark.parametrize(
    "func,val,expected_op",
    [
        (exp.int_val, 42, "int_val"),
        (exp.int_val, 0, "int_val"),
        (exp.int_val, -1, "int_val"),
        (exp.int_val, 2**63 - 1, "int_val"),
        (exp.int_val, -(2**63), "int_val"),
        (exp.float_val, 3.14, "float_val"),
        (exp.float_val, 0.0, "float_val"),
        (exp.float_val, -1.5, "float_val"),
        (exp.float_val, float("inf"), "float_val"),
        (exp.string_val, "hello", "string_val"),
        (exp.string_val, "", "string_val"),
        (exp.string_val, "a" * 1000, "string_val"),
        (exp.bool_val, True, "bool_val"),
        (exp.bool_val, False, "bool_val"),
        (exp.blob_val, b"\x01\x02", "blob_val"),
        (exp.blob_val, b"", "blob_val"),
        (exp.list_val, [1, 2, 3], "list_val"),
        (exp.list_val, [], "list_val"),
        (exp.list_val, [None, "a", 1, 3.14], "list_val"),
        (exp.map_val, {"a": 1}, "map_val"),
        (exp.map_val, {}, "map_val"),
        (exp.geo_val, '{"type":"Point","coordinates":[0.0,0.0]}', "geo_val"),
    ],
    ids=[
        "int_42",
        "int_0",
        "int_neg",
        "int_max64",
        "int_min64",
        "float_pi",
        "float_zero",
        "float_neg",
        "float_inf",
        "string_hello",
        "string_empty",
        "string_long",
        "bool_true",
        "bool_false",
        "blob_bytes",
        "blob_empty",
        "list_ints",
        "list_empty",
        "list_mixed",
        "map_simple",
        "map_empty",
        "geo_point",
    ],
)
def test_value_constructors(func, val, expected_op):
    """Value constructor functions produce correct expression dicts."""
    e = func(val)
    assert e["__expr__"] == expected_op
    assert e["val"] == val


@pytest.mark.parametrize(
    "func,expected_op",
    [
        (exp.nil, "nil"),
        (exp.infinity, "infinity"),
        (exp.wildcard, "wildcard"),
    ],
)
def test_sentinel_constructors(func, expected_op):
    """Sentinel constructors (nil, infinity, wildcard) produce correct expression dicts."""
    e = func()
    assert e["__expr__"] == expected_op
    assert "val" not in e


# ── Parametrized bin accessor tests ─────────────────────────────────


@pytest.mark.parametrize(
    "func,expected_op",
    [
        (exp.int_bin, "int_bin"),
        (exp.float_bin, "float_bin"),
        (exp.string_bin, "string_bin"),
        (exp.bool_bin, "bool_bin"),
        (exp.blob_bin, "blob_bin"),
        (exp.list_bin, "list_bin"),
        (exp.map_bin, "map_bin"),
        (exp.geo_bin, "geo_bin"),
        (exp.hll_bin, "hll_bin"),
        (exp.bin_exists, "bin_exists"),
        (exp.bin_type, "bin_type"),
    ],
)
def test_bin_accessors(func, expected_op):
    """Bin accessor functions produce correct expression dicts."""
    e = func("mybin")
    assert e["__expr__"] == expected_op
    assert e["name"] == "mybin"


@pytest.mark.parametrize(
    "bin_name",
    ["age", "", "a" * 15, "special-chars_123"],
    ids=["normal", "empty", "long_name", "special_chars"],
)
def test_bin_accessor_various_names(bin_name):
    """Bin accessors work with various bin name patterns."""
    e = exp.int_bin(bin_name)
    assert e["name"] == bin_name


# ── Record metadata tests ──────────────────────────────────────────


@pytest.mark.parametrize(
    "func,expected_op",
    [
        (exp.key_exists, "key_exists"),
        (exp.set_name, "set_name"),
        (exp.record_size, "record_size"),
        (exp.ttl, "ttl"),
        (exp.last_update, "last_update"),
        (exp.since_update, "since_update"),
        (exp.void_time, "void_time"),
        (exp.is_tombstone, "is_tombstone"),
    ],
)
def test_record_metadata_no_args(func, expected_op):
    """Record metadata functions without args produce correct expression dicts."""
    e = func()
    assert e["__expr__"] == expected_op


def test_key_with_type():
    e = exp.key(exp.EXP_TYPE_INT)
    assert e["__expr__"] == "key"
    assert e["exp_type"] == 2


@pytest.mark.parametrize("modulo", [1, 3, 100, 4096])
def test_digest_modulo_various(modulo):
    e = exp.digest_modulo(modulo)
    assert e["__expr__"] == "digest_modulo"
    assert e["modulo"] == modulo


# ── Parametrized comparison tests ──────────────────────────────────


@pytest.mark.parametrize(
    "func,expected_op",
    [
        (exp.eq, "eq"),
        (exp.ne, "ne"),
        (exp.gt, "gt"),
        (exp.ge, "ge"),
        (exp.lt, "lt"),
        (exp.le, "le"),
    ],
)
def test_comparisons(func, expected_op):
    """All comparison operators produce correct expression structure."""
    e = func(exp.int_bin("age"), exp.int_val(21))
    assert e["__expr__"] == expected_op
    assert e["left"]["__expr__"] == "int_bin"
    assert e["right"]["__expr__"] == "int_val"


# ── Logical operation tests ────────────────────────────────────────


class TestExpLogical:
    def test_and(self):
        e = exp.and_(
            exp.ge(exp.int_bin("age"), exp.int_val(18)),
            exp.lt(exp.int_bin("age"), exp.int_val(65)),
        )
        assert e["__expr__"] == "and"
        assert len(e["exprs"]) == 2

    def test_or(self):
        e = exp.or_(
            exp.eq(exp.string_bin("role"), exp.string_val("admin")),
            exp.eq(exp.string_bin("role"), exp.string_val("superuser")),
        )
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 2

    def test_not(self):
        e = exp.not_(exp.eq(exp.int_bin("deleted"), exp.int_val(1)))
        assert e["__expr__"] == "not"
        assert e["expr"]["__expr__"] == "eq"

    def test_xor(self):
        e = exp.xor_(exp.bool_val(True), exp.bool_val(False))
        assert e["__expr__"] == "xor"
        assert len(e["exprs"]) == 2

    def test_and_many_operands(self):
        """and_ should accept more than 2 operands."""
        e = exp.and_(
            exp.bool_val(True),
            exp.bool_val(True),
            exp.bool_val(False),
        )
        assert e["__expr__"] == "and"
        assert len(e["exprs"]) == 3

    def test_or_many_operands(self):
        """or_ should accept more than 2 operands."""
        e = exp.or_(
            exp.bool_val(True),
            exp.bool_val(False),
            exp.bool_val(True),
            exp.bool_val(False),
        )
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 4


# ── Numeric operation tests ────────────────────────────────────────


@pytest.mark.parametrize(
    "func,expected_op,num_args",
    [
        (lambda: exp.num_add(exp.int_bin("a"), exp.int_val(1)), "num_add", 2),
        (lambda: exp.num_sub(exp.int_bin("a"), exp.int_val(1)), "num_sub", 2),
        (lambda: exp.num_mul(exp.int_bin("a"), exp.int_val(2)), "num_mul", 2),
        (lambda: exp.num_div(exp.int_bin("a"), exp.int_val(2)), "num_div", 2),
        (lambda: exp.num_mod(exp.int_bin("counter"), exp.int_val(10)), "num_mod", 2),
        (lambda: exp.num_pow(exp.int_bin("base"), exp.int_val(2)), "num_pow", 2),
        (lambda: exp.num_log(exp.int_bin("val"), exp.int_val(10)), "num_log", 2),
        (lambda: exp.num_abs(exp.int_bin("val")), "num_abs", 1),
        (lambda: exp.num_floor(exp.float_bin("f")), "num_floor", 1),
        (lambda: exp.num_ceil(exp.float_bin("f")), "num_ceil", 1),
        (lambda: exp.to_int(exp.float_bin("score")), "to_int", 1),
        (lambda: exp.to_float(exp.int_bin("count")), "to_float", 1),
    ],
    ids=[
        "add",
        "sub",
        "mul",
        "div",
        "mod",
        "pow",
        "log",
        "abs",
        "floor",
        "ceil",
        "to_int",
        "to_float",
    ],
)
def test_numeric_operations(func, expected_op, num_args):
    """Numeric operations produce correct expression dicts."""
    e = func()
    assert e["__expr__"] == expected_op
    assert len(e["exprs"]) == num_args


# ── Integer bitwise operation tests ─────────────────────────────────


@pytest.mark.parametrize(
    "func,expected_op,num_args",
    [
        (lambda: exp.int_and(exp.int_bin("flags"), exp.int_val(0xFF)), "int_and", 2),
        (lambda: exp.int_or(exp.int_bin("flags"), exp.int_val(0x01)), "int_or", 2),
        (lambda: exp.int_xor(exp.int_bin("flags"), exp.int_val(0x0F)), "int_xor", 2),
        (lambda: exp.int_not(exp.int_bin("flags")), "int_not", 1),
        (lambda: exp.int_lshift(exp.int_bin("v"), exp.int_val(2)), "int_lshift", 2),
        (lambda: exp.int_rshift(exp.int_bin("v"), exp.int_val(2)), "int_rshift", 2),
        (lambda: exp.int_arshift(exp.int_bin("v"), exp.int_val(2)), "int_arshift", 2),
        (lambda: exp.int_count(exp.int_bin("flags")), "int_count", 1),
        (lambda: exp.int_lscan(exp.int_bin("v"), exp.int_val(1)), "int_lscan", 2),
        (lambda: exp.int_rscan(exp.int_bin("v"), exp.int_val(0)), "int_rscan", 2),
    ],
    ids=[
        "and",
        "or",
        "xor",
        "not",
        "lshift",
        "rshift",
        "arshift",
        "count",
        "lscan",
        "rscan",
    ],
)
def test_int_bitwise_operations(func, expected_op, num_args):
    """Integer bitwise operations produce correct expression dicts."""
    e = func()
    assert e["__expr__"] == expected_op
    assert len(e["exprs"]) == num_args


# ── Pattern matching tests ──────────────────────────────────────────


class TestExpPatternMatching:
    def test_regex_compare(self):
        e = exp.regex_compare("prefix.*", 0, exp.string_bin("name"))
        assert e["__expr__"] == "regex_compare"
        assert e["regex"] == "prefix.*"
        assert e["flags"] == 0
        assert e["bin"]["__expr__"] == "string_bin"

    def test_geo_compare(self):
        e = exp.geo_compare(exp.geo_bin("loc"), exp.geo_val('{"type":"Point"}'))
        assert e["__expr__"] == "geo_compare"


# ── Control flow tests ──────────────────────────────────────────────


class TestExpControlFlow:
    def test_cond(self):
        e = exp.cond(
            exp.eq(exp.int_bin("type"), exp.int_val(1)),
            exp.string_val("type_a"),
            exp.string_val("other"),
        )
        assert e["__expr__"] == "cond"
        assert len(e["exprs"]) == 3

    def test_let_and_var(self):
        e = exp.let_(
            exp.def_("x", exp.int_bin("count")),
            exp.gt(exp.var("x"), exp.int_val(0)),
        )
        assert e["__expr__"] == "let"
        assert len(e["exprs"]) == 2
        assert e["exprs"][0]["__expr__"] == "def"
        assert e["exprs"][0]["name"] == "x"

    def test_var_standalone(self):
        e = exp.var("myvar")
        assert e["__expr__"] == "var"
        assert e["name"] == "myvar"

    def test_def_standalone(self):
        e = exp.def_("x", exp.int_val(42))
        assert e["__expr__"] == "def"
        assert e["name"] == "x"
        assert e["value"]["val"] == 42


# ── Type constants tests ───────────────────────────────────────────


@pytest.mark.parametrize(
    "constant,expected_value",
    [
        (exp.EXP_TYPE_NIL, 0),
        (exp.EXP_TYPE_BOOL, 1),
        (exp.EXP_TYPE_INT, 2),
        (exp.EXP_TYPE_STRING, 3),
        (exp.EXP_TYPE_LIST, 4),
        (exp.EXP_TYPE_MAP, 5),
        (exp.EXP_TYPE_BLOB, 6),
        (exp.EXP_TYPE_FLOAT, 7),
        (exp.EXP_TYPE_GEO, 8),
        (exp.EXP_TYPE_HLL, 9),
    ],
)
def test_type_constants(constant, expected_value):
    """Expression type constants have expected values."""
    assert constant == expected_value


# ── Module access tests ─────────────────────────────────────────────


class TestExpModuleAccess:
    def test_exp_module(self):
        assert hasattr(exp, "eq")
        assert hasattr(exp, "int_bin")
        assert hasattr(exp, "and_")
        assert hasattr(exp, "ttl")
        assert hasattr(exp, "regex_compare")

    def test_exp_all_exports(self):
        """Every symbol in __all__ should be importable from the exp module."""
        for name in exp.__all__:
            assert hasattr(exp, name), f"exp.__all__ contains '{name}' but it is not defined"


# ── Complex expression tests ────────────────────────────────────────


class TestExpComplexExpressions:
    def test_nested_and_or(self):
        """Test complex nested expression: (age >= 18 AND age < 65) OR role == 'admin'."""
        e = exp.or_(
            exp.and_(
                exp.ge(exp.int_bin("age"), exp.int_val(18)),
                exp.lt(exp.int_bin("age"), exp.int_val(65)),
            ),
            exp.eq(exp.string_bin("role"), exp.string_val("admin")),
        )
        assert e["__expr__"] == "or"
        assert len(e["exprs"]) == 2
        assert e["exprs"][0]["__expr__"] == "and"
        assert len(e["exprs"][0]["exprs"]) == 2

    def test_expression_in_policy_dict(self):
        """Test that expressions can be embedded in policy dicts."""
        expr = exp.ge(exp.int_bin("age"), exp.int_val(21))
        policy = {"filter_expression": expr, "socket_timeout": 5000}
        assert policy["filter_expression"]["__expr__"] == "ge"
        assert policy["socket_timeout"] == 5000

    def test_deeply_nested_expression(self):
        """Test a 3-level deep nested expression."""
        e = exp.and_(
            exp.or_(
                exp.eq(exp.int_bin("a"), exp.int_val(1)),
                exp.not_(
                    exp.eq(exp.int_bin("b"), exp.int_val(2)),
                ),
            ),
            exp.ge(exp.float_bin("score"), exp.float_val(0.5)),
        )
        assert e["__expr__"] == "and"
        inner_or = e["exprs"][0]
        assert inner_or["__expr__"] == "or"
        inner_not = inner_or["exprs"][1]
        assert inner_not["__expr__"] == "not"
        assert inner_not["expr"]["__expr__"] == "eq"


# ── Invalid op tests ───────────────────────────────────────────────


def test_exp_invalid_op_rejected():
    """Constructing an expression with invalid op raises ValueError."""
    with pytest.raises(ValueError, match="nonexistent_op"):
        exp._cmd("nonexistent_op", val=42)
