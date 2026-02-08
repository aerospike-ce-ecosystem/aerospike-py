"""Expression filter builder for Aerospike server-side filtering (Server >= 5.2).

Usage example::

    from aerospike_py import exp

    # Filter: bin "age" >= 21
    expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

    # Filter: bin "name" == "Alice" AND bin "active" == True
    expr = exp.and_(
        exp.eq(exp.string_bin("name"), exp.string_val("Alice")),
        exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
    )

    # Pass to policy
    policy = {"filter_expression": expr}
    client.get(key, policy=policy)
"""

from typing import Any

# Type alias for expression nodes returned by builder functions
Expr = dict[str, Any]

# Expression type constants
EXP_TYPE_NIL = 0
EXP_TYPE_BOOL = 1
EXP_TYPE_INT = 2
EXP_TYPE_STRING = 3
EXP_TYPE_LIST = 4
EXP_TYPE_MAP = 5
EXP_TYPE_BLOB = 6
EXP_TYPE_FLOAT = 7
EXP_TYPE_GEO = 8
EXP_TYPE_HLL = 9


def _cmd(op: str, **kwargs: Any) -> Expr:
    """Build an expression node dict."""
    result: Expr = {"__expr__": op}
    result.update(kwargs)
    return result


# ── Value constructors ──────────────────────────────────────────────


def int_val(val: int) -> Expr:
    """Create 64-bit integer value expression."""
    return _cmd("int_val", val=val)


def float_val(val: float) -> Expr:
    """Create 64-bit float value expression."""
    return _cmd("float_val", val=val)


def string_val(val: str) -> Expr:
    """Create string value expression."""
    return _cmd("string_val", val=val)


def bool_val(val: bool) -> Expr:
    """Create boolean value expression."""
    return _cmd("bool_val", val=val)


def blob_val(val: bytes) -> Expr:
    """Create blob (bytes) value expression."""
    return _cmd("blob_val", val=val)


def list_val(val: list[Any]) -> Expr:
    """Create list value expression."""
    return _cmd("list_val", val=val)


def map_val(val: dict[Any, Any]) -> Expr:
    """Create map value expression."""
    return _cmd("map_val", val=val)


def geo_val(val: str) -> Expr:
    """Create geospatial JSON string value expression."""
    return _cmd("geo_val", val=val)


def nil() -> Expr:
    """Create nil value expression."""
    return _cmd("nil")


def infinity() -> Expr:
    """Create infinity value expression."""
    return _cmd("infinity")


def wildcard() -> Expr:
    """Create wildcard value expression."""
    return _cmd("wildcard")


# ── Bin accessors ───────────────────────────────────────────────────


def int_bin(name: str) -> Expr:
    """Create 64-bit integer bin expression."""
    return _cmd("int_bin", name=name)


def float_bin(name: str) -> Expr:
    """Create 64-bit float bin expression."""
    return _cmd("float_bin", name=name)


def string_bin(name: str) -> Expr:
    """Create string bin expression."""
    return _cmd("string_bin", name=name)


def bool_bin(name: str) -> Expr:
    """Create boolean bin expression."""
    return _cmd("bool_bin", name=name)


def blob_bin(name: str) -> Expr:
    """Create blob bin expression."""
    return _cmd("blob_bin", name=name)


def list_bin(name: str) -> Expr:
    """Create list bin expression."""
    return _cmd("list_bin", name=name)


def map_bin(name: str) -> Expr:
    """Create map bin expression."""
    return _cmd("map_bin", name=name)


def geo_bin(name: str) -> Expr:
    """Create geospatial bin expression."""
    return _cmd("geo_bin", name=name)


def hll_bin(name: str) -> Expr:
    """Create HyperLogLog bin expression."""
    return _cmd("hll_bin", name=name)


def bin_exists(name: str) -> Expr:
    """Create expression that returns true if bin exists."""
    return _cmd("bin_exists", name=name)


def bin_type(name: str) -> Expr:
    """Create expression that returns bin's particle type."""
    return _cmd("bin_type", name=name)


# ── Record metadata ────────────────────────────────────────────────


def key(exp_type: int) -> Expr:
    """Create record key expression of specified type."""
    return _cmd("key", exp_type=exp_type)


def key_exists() -> Expr:
    """Create expression that returns if primary key is stored in record metadata."""
    return _cmd("key_exists")


def set_name() -> Expr:
    """Create expression that returns record set name."""
    return _cmd("set_name")


def record_size() -> Expr:
    """Create expression that returns record size (server 7.0+)."""
    return _cmd("record_size")


def last_update() -> Expr:
    """Create expression that returns record last update time (nanoseconds since epoch)."""
    return _cmd("last_update")


def since_update() -> Expr:
    """Create expression that returns milliseconds since last update."""
    return _cmd("since_update")


def void_time() -> Expr:
    """Create expression that returns record expiration time (nanoseconds since epoch)."""
    return _cmd("void_time")


def ttl() -> Expr:
    """Create expression that returns record TTL in seconds."""
    return _cmd("ttl")


def is_tombstone() -> Expr:
    """Create expression that returns if record is in tombstone state."""
    return _cmd("is_tombstone")


def digest_modulo(modulo: int) -> Expr:
    """Create expression that returns record digest modulo."""
    return _cmd("digest_modulo", modulo=modulo)


# ── Comparison operations ──────────────────────────────────────────


def eq(left: Expr, right: Expr) -> Expr:
    """Create equal (==) expression."""
    return _cmd("eq", left=left, right=right)


def ne(left: Expr, right: Expr) -> Expr:
    """Create not equal (!=) expression."""
    return _cmd("ne", left=left, right=right)


def gt(left: Expr, right: Expr) -> Expr:
    """Create greater than (>) expression."""
    return _cmd("gt", left=left, right=right)


def ge(left: Expr, right: Expr) -> Expr:
    """Create greater than or equal (>=) expression."""
    return _cmd("ge", left=left, right=right)


def lt(left: Expr, right: Expr) -> Expr:
    """Create less than (<) expression."""
    return _cmd("lt", left=left, right=right)


def le(left: Expr, right: Expr) -> Expr:
    """Create less than or equal (<=) expression."""
    return _cmd("le", left=left, right=right)


# ── Logical operations ─────────────────────────────────────────────


def and_(*exprs: Expr) -> Expr:
    """Create logical AND expression."""
    return _cmd("and", exprs=list(exprs))


def or_(*exprs: Expr) -> Expr:
    """Create logical OR expression."""
    return _cmd("or", exprs=list(exprs))


def not_(expr: Expr) -> Expr:
    """Create logical NOT expression."""
    return _cmd("not", expr=expr)


def xor_(*exprs: Expr) -> Expr:
    """Create logical XOR expression."""
    return _cmd("xor", exprs=list(exprs))


# ── Numeric operations ─────────────────────────────────────────────


def num_add(*exprs: Expr) -> Expr:
    """Create numeric add expression."""
    return _cmd("num_add", exprs=list(exprs))


def num_sub(*exprs: Expr) -> Expr:
    """Create numeric subtract expression."""
    return _cmd("num_sub", exprs=list(exprs))


def num_mul(*exprs: Expr) -> Expr:
    """Create numeric multiply expression."""
    return _cmd("num_mul", exprs=list(exprs))


def num_div(*exprs: Expr) -> Expr:
    """Create numeric divide expression."""
    return _cmd("num_div", exprs=list(exprs))


def num_mod(numerator: Expr, denominator: Expr) -> Expr:
    """Create numeric modulo expression."""
    return _cmd("num_mod", exprs=[numerator, denominator])


def num_pow(base: Expr, exponent: Expr) -> Expr:
    """Create numeric power expression."""
    return _cmd("num_pow", exprs=[base, exponent])


def num_log(num: Expr, base: Expr) -> Expr:
    """Create numeric log expression."""
    return _cmd("num_log", exprs=[num, base])


def num_abs(value: Expr) -> Expr:
    """Create numeric absolute value expression."""
    return _cmd("num_abs", exprs=[value])


def num_floor(num: Expr) -> Expr:
    """Create numeric floor expression."""
    return _cmd("num_floor", exprs=[num])


def num_ceil(num: Expr) -> Expr:
    """Create numeric ceil expression."""
    return _cmd("num_ceil", exprs=[num])


def to_int(num: Expr) -> Expr:
    """Create convert-to-integer expression."""
    return _cmd("to_int", exprs=[num])


def to_float(num: Expr) -> Expr:
    """Create convert-to-float expression."""
    return _cmd("to_float", exprs=[num])


def min_(*exprs: Expr) -> Expr:
    """Create minimum value expression."""
    return _cmd("min", exprs=list(exprs))


def max_(*exprs: Expr) -> Expr:
    """Create maximum value expression."""
    return _cmd("max", exprs=list(exprs))


# ── Integer bitwise operations ─────────────────────────────────────


def int_and(*exprs: Expr) -> Expr:
    """Create integer bitwise AND expression."""
    return _cmd("int_and", exprs=list(exprs))


def int_or(*exprs: Expr) -> Expr:
    """Create integer bitwise OR expression."""
    return _cmd("int_or", exprs=list(exprs))


def int_xor(*exprs: Expr) -> Expr:
    """Create integer bitwise XOR expression."""
    return _cmd("int_xor", exprs=list(exprs))


def int_not(expr: Expr) -> Expr:
    """Create integer bitwise NOT expression."""
    return _cmd("int_not", exprs=[expr])


def int_lshift(value: Expr, shift: Expr) -> Expr:
    """Create integer left shift expression."""
    return _cmd("int_lshift", exprs=[value, shift])


def int_rshift(value: Expr, shift: Expr) -> Expr:
    """Create integer logical right shift expression."""
    return _cmd("int_rshift", exprs=[value, shift])


def int_arshift(value: Expr, shift: Expr) -> Expr:
    """Create integer arithmetic right shift expression."""
    return _cmd("int_arshift", exprs=[value, shift])


def int_count(expr: Expr) -> Expr:
    """Create integer bit count expression."""
    return _cmd("int_count", exprs=[expr])


def int_lscan(value: Expr, search: Expr) -> Expr:
    """Create integer scan from MSB expression."""
    return _cmd("int_lscan", exprs=[value, search])


def int_rscan(value: Expr, search: Expr) -> Expr:
    """Create integer scan from LSB expression."""
    return _cmd("int_rscan", exprs=[value, search])


# ── Pattern matching ───────────────────────────────────────────────


def regex_compare(regex: str, flags: int, bin_expr: Expr) -> Expr:
    """Create regex string comparison expression."""
    return _cmd("regex_compare", regex=regex, flags=flags, bin=bin_expr)


def geo_compare(left: Expr, right: Expr) -> Expr:
    """Create geospatial comparison expression."""
    return _cmd("geo_compare", left=left, right=right)


# ── Variables and control flow ─────────────────────────────────────


def cond(*exprs: Expr) -> Expr:
    """Create conditional expression: cond(bool1, action1, bool2, action2, ..., default)."""
    return _cmd("cond", exprs=list(exprs))


def var(name: str) -> Expr:
    """Create variable reference expression."""
    return _cmd("var", name=name)


def def_(name: str, value: Expr) -> Expr:
    """Create variable definition expression (used with let_)."""
    return _cmd("def", name=name, value=value)


def let_(*exprs: Expr) -> Expr:
    """Create let binding expression: let_(def_("x", ...), def_("y", ...), scope_expr)."""
    return _cmd("let", exprs=list(exprs))
