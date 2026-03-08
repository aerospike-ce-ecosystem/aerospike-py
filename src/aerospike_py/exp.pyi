"""Type stubs for exp (expression filter) module.

Expression filter builder for Aerospike server-side filtering (Server >= 5.2).

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

Expr = dict[str, Any]

# Expression type constants
EXP_TYPE_NIL: int
EXP_TYPE_BOOL: int
EXP_TYPE_INT: int
EXP_TYPE_STRING: int
EXP_TYPE_LIST: int
EXP_TYPE_MAP: int
EXP_TYPE_BLOB: int
EXP_TYPE_FLOAT: int
EXP_TYPE_GEO: int
EXP_TYPE_HLL: int

# ── Value constructors ──────────────────────────────────────────────

def int_val(val: int) -> Expr:
    """Create 64-bit integer value expression."""
    ...

def float_val(val: float) -> Expr:
    """Create 64-bit float value expression."""
    ...

def string_val(val: str) -> Expr:
    """Create string value expression."""
    ...

def bool_val(val: bool) -> Expr:
    """Create boolean value expression."""
    ...

def blob_val(val: bytes) -> Expr:
    """Create blob (bytes) value expression."""
    ...

def list_val(val: list[Any]) -> Expr:
    """Create list value expression."""
    ...

def map_val(val: dict[Any, Any]) -> Expr:
    """Create map value expression."""
    ...

def geo_val(val: str) -> Expr:
    """Create geospatial JSON string value expression."""
    ...

def nil() -> Expr:
    """Create nil value expression."""
    ...

def infinity() -> Expr:
    """Create infinity value expression."""
    ...

def wildcard() -> Expr:
    """Create wildcard value expression."""
    ...

# ── Bin accessors ───────────────────────────────────────────────────

def int_bin(name: str) -> Expr:
    """Create 64-bit integer bin expression."""
    ...

def float_bin(name: str) -> Expr:
    """Create 64-bit float bin expression."""
    ...

def string_bin(name: str) -> Expr:
    """Create string bin expression."""
    ...

def bool_bin(name: str) -> Expr:
    """Create boolean bin expression."""
    ...

def blob_bin(name: str) -> Expr:
    """Create blob bin expression."""
    ...

def list_bin(name: str) -> Expr:
    """Create list bin expression."""
    ...

def map_bin(name: str) -> Expr:
    """Create map bin expression."""
    ...

def geo_bin(name: str) -> Expr:
    """Create geospatial bin expression."""
    ...

def hll_bin(name: str) -> Expr:
    """Create HyperLogLog bin expression."""
    ...

def bin_exists(name: str) -> Expr:
    """Create expression that returns true if bin exists."""
    ...

def bin_type(name: str) -> Expr:
    """Create expression that returns bin's particle type."""
    ...

# ── Record metadata ────────────────────────────────────────────────

def key(exp_type: int) -> Expr:
    """Create record key expression of specified type."""
    ...

def key_exists() -> Expr:
    """Create expression that returns if primary key is stored in record metadata."""
    ...

def set_name() -> Expr:
    """Create expression that returns record set name."""
    ...

def record_size() -> Expr:
    """Create expression that returns record size (server 7.0+)."""
    ...

def last_update() -> Expr:
    """Create expression that returns record last update time (nanoseconds since epoch)."""
    ...

def since_update() -> Expr:
    """Create expression that returns milliseconds since last update."""
    ...

def void_time() -> Expr:
    """Create expression that returns record expiration time (nanoseconds since epoch)."""
    ...

def ttl() -> Expr:
    """Create expression that returns record TTL in seconds."""
    ...

def is_tombstone() -> Expr:
    """Create expression that returns if record is in tombstone state."""
    ...

def digest_modulo(modulo: int) -> Expr:
    """Create expression that returns record digest modulo."""
    ...

# ── Comparison operations ──────────────────────────────────────────

def eq(left: Expr, right: Expr) -> Expr:
    """Create equal (==) expression."""
    ...

def ne(left: Expr, right: Expr) -> Expr:
    """Create not equal (!=) expression."""
    ...

def gt(left: Expr, right: Expr) -> Expr:
    """Create greater than (>) expression."""
    ...

def ge(left: Expr, right: Expr) -> Expr:
    """Create greater than or equal (>=) expression."""
    ...

def lt(left: Expr, right: Expr) -> Expr:
    """Create less than (<) expression."""
    ...

def le(left: Expr, right: Expr) -> Expr:
    """Create less than or equal (<=) expression."""
    ...

# ── Logical operations ─────────────────────────────────────────────

def and_(*exprs: Expr) -> Expr:
    """Create logical AND expression."""
    ...

def or_(*exprs: Expr) -> Expr:
    """Create logical OR expression."""
    ...

def not_(expr: Expr) -> Expr:
    """Create logical NOT expression."""
    ...

def xor_(*exprs: Expr) -> Expr:
    """Create logical XOR expression."""
    ...

# ── Numeric operations ─────────────────────────────────────────────

def num_add(*exprs: Expr) -> Expr:
    """Create numeric add expression."""
    ...

def num_sub(*exprs: Expr) -> Expr:
    """Create numeric subtract expression."""
    ...

def num_mul(*exprs: Expr) -> Expr:
    """Create numeric multiply expression."""
    ...

def num_div(*exprs: Expr) -> Expr:
    """Create numeric divide expression."""
    ...

def num_mod(numerator: Expr, denominator: Expr) -> Expr:
    """Create numeric modulo expression."""
    ...

def num_pow(base: Expr, exponent: Expr) -> Expr:
    """Create numeric power expression."""
    ...

def num_log(num: Expr, base: Expr) -> Expr:
    """Create numeric log expression."""
    ...

def num_abs(value: Expr) -> Expr:
    """Create numeric absolute value expression."""
    ...

def num_floor(num: Expr) -> Expr:
    """Create numeric floor expression."""
    ...

def num_ceil(num: Expr) -> Expr:
    """Create numeric ceil expression."""
    ...

def to_int(num: Expr) -> Expr:
    """Create convert-to-integer expression."""
    ...

def to_float(num: Expr) -> Expr:
    """Create convert-to-float expression."""
    ...

def min_(*exprs: Expr) -> Expr:
    """Create minimum value expression."""
    ...

def max_(*exprs: Expr) -> Expr:
    """Create maximum value expression."""
    ...

# ── Integer bitwise operations ─────────────────────────────────────

def int_and(*exprs: Expr) -> Expr:
    """Create integer bitwise AND expression."""
    ...

def int_or(*exprs: Expr) -> Expr:
    """Create integer bitwise OR expression."""
    ...

def int_xor(*exprs: Expr) -> Expr:
    """Create integer bitwise XOR expression."""
    ...

def int_not(expr: Expr) -> Expr:
    """Create integer bitwise NOT expression."""
    ...

def int_lshift(value: Expr, shift: Expr) -> Expr:
    """Create integer left shift expression."""
    ...

def int_rshift(value: Expr, shift: Expr) -> Expr:
    """Create integer logical right shift expression."""
    ...

def int_arshift(value: Expr, shift: Expr) -> Expr:
    """Create integer arithmetic right shift expression."""
    ...

def int_count(expr: Expr) -> Expr:
    """Create integer bit count expression."""
    ...

def int_lscan(value: Expr, search: Expr) -> Expr:
    """Create integer scan from MSB expression."""
    ...

def int_rscan(value: Expr, search: Expr) -> Expr:
    """Create integer scan from LSB expression."""
    ...

# ── Pattern matching ───────────────────────────────────────────────

def regex_compare(regex: str, flags: int, bin_expr: Expr) -> Expr:
    """Create regex string comparison expression."""
    ...

def geo_compare(left: Expr, right: Expr) -> Expr:
    """Create geospatial comparison expression."""
    ...

# ── Variables and control flow ─────────────────────────────────────

def cond(*exprs: Expr) -> Expr:
    """Create conditional expression: cond(bool1, action1, bool2, action2, ..., default)."""
    ...

def var(name: str) -> Expr:
    """Create variable reference expression."""
    ...

def def_(name: str, value: Expr) -> Expr:
    """Create variable definition expression (used with let_)."""
    ...

def let_(*exprs: Expr) -> Expr:
    """Create let binding expression: let_(def_("x", ...), def_("y", ...), scope_expr)."""
    ...
