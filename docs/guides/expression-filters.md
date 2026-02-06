# Expression Filters

Expression Filters allow server-side filtering of records during read, write, query, and scan operations. The server evaluates the expression and only returns (or modifies) records that match.

!!! note "Server Requirement"
    Expression filters require Aerospike Server **5.2+**.

## Import

```python
from aerospike_py import exp
```

## Overview

Expressions are built by composing function calls that return dict nodes. These dicts are passed to the Rust layer via the `filter_expression` policy key, where they are compiled into the Aerospike wire-format.

```python
# Build expression: age >= 21
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Use in policy
policy = {"filter_expression": expr}
_, _, bins = client.get(key, policy=policy)
```

## Value Constructors

Create literal value expressions:

| Function | Description |
|----------|-------------|
| `exp.int_val(val)` | 64-bit integer |
| `exp.float_val(val)` | 64-bit float |
| `exp.string_val(val)` | String |
| `exp.bool_val(val)` | Boolean |
| `exp.blob_val(val)` | Bytes |
| `exp.list_val(val)` | List |
| `exp.map_val(val)` | Map/dict |
| `exp.geo_val(val)` | GeoJSON string |
| `exp.nil()` | Nil value |
| `exp.infinity()` | Infinity (for unbounded ranges) |
| `exp.wildcard()` | Wildcard (matches any value) |

```python
exp.int_val(42)
exp.string_val("hello")
exp.bool_val(True)
exp.list_val([1, 2, 3])
exp.map_val({"key": "value"})
```

## Bin Accessors

Read bin values by type:

| Function | Description |
|----------|-------------|
| `exp.int_bin(name)` | Read integer bin |
| `exp.float_bin(name)` | Read float bin |
| `exp.string_bin(name)` | Read string bin |
| `exp.bool_bin(name)` | Read boolean bin |
| `exp.blob_bin(name)` | Read blob bin |
| `exp.list_bin(name)` | Read list bin |
| `exp.map_bin(name)` | Read map bin |
| `exp.geo_bin(name)` | Read geospatial bin |
| `exp.hll_bin(name)` | Read HyperLogLog bin |
| `exp.bin_exists(name)` | True if bin exists |
| `exp.bin_type(name)` | Bin particle type |

```python
exp.int_bin("age")
exp.string_bin("name")
exp.bin_exists("optional_field")
```

## Comparison Operations

| Function | Description |
|----------|-------------|
| `exp.eq(left, right)` | Equal (`==`) |
| `exp.ne(left, right)` | Not equal (`!=`) |
| `exp.gt(left, right)` | Greater than (`>`) |
| `exp.ge(left, right)` | Greater or equal (`>=`) |
| `exp.lt(left, right)` | Less than (`<`) |
| `exp.le(left, right)` | Less or equal (`<=`) |

```python
# age == 30
exp.eq(exp.int_bin("age"), exp.int_val(30))

# score > 100.5
exp.gt(exp.float_bin("score"), exp.float_val(100.5))

# name != "admin"
exp.ne(exp.string_bin("name"), exp.string_val("admin"))
```

## Logical Operations

| Function | Description |
|----------|-------------|
| `exp.and_(*exprs)` | Logical AND |
| `exp.or_(*exprs)` | Logical OR |
| `exp.not_(expr)` | Logical NOT |
| `exp.xor_(*exprs)` | Logical XOR |

```python
# age >= 18 AND active == true
exp.and_(
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
)

# status == "gold" OR status == "platinum"
exp.or_(
    exp.eq(exp.string_bin("status"), exp.string_val("gold")),
    exp.eq(exp.string_bin("status"), exp.string_val("platinum")),
)

# NOT deleted
exp.not_(exp.eq(exp.bool_bin("deleted"), exp.bool_val(True)))
```

## Numeric Operations

| Function | Description |
|----------|-------------|
| `exp.num_add(*exprs)` | Addition |
| `exp.num_sub(*exprs)` | Subtraction |
| `exp.num_mul(*exprs)` | Multiplication |
| `exp.num_div(*exprs)` | Division |
| `exp.num_mod(num, denom)` | Modulo |
| `exp.num_pow(base, exponent)` | Power |
| `exp.num_log(num, base)` | Logarithm |
| `exp.num_abs(value)` | Absolute value |
| `exp.num_floor(num)` | Floor |
| `exp.num_ceil(num)` | Ceiling |
| `exp.to_int(num)` | Convert to integer |
| `exp.to_float(num)` | Convert to float |
| `exp.min_(*exprs)` | Minimum value |
| `exp.max_(*exprs)` | Maximum value |

```python
# (price * quantity) > 1000
exp.gt(
    exp.num_mul(exp.int_bin("price"), exp.int_bin("quantity")),
    exp.int_val(1000),
)
```

## Integer Bitwise Operations

| Function | Description |
|----------|-------------|
| `exp.int_and(*exprs)` | Bitwise AND |
| `exp.int_or(*exprs)` | Bitwise OR |
| `exp.int_xor(*exprs)` | Bitwise XOR |
| `exp.int_not(expr)` | Bitwise NOT |
| `exp.int_lshift(value, shift)` | Left shift |
| `exp.int_rshift(value, shift)` | Logical right shift |
| `exp.int_arshift(value, shift)` | Arithmetic right shift |
| `exp.int_count(expr)` | Bit count |
| `exp.int_lscan(value, search)` | Scan from MSB |
| `exp.int_rscan(value, search)` | Scan from LSB |

## Record Metadata

| Function | Description |
|----------|-------------|
| `exp.key(exp_type)` | Record primary key |
| `exp.key_exists()` | True if key stored in metadata |
| `exp.set_name()` | Record set name |
| `exp.record_size()` | Record size in bytes (Server 7.0+) |
| `exp.last_update()` | Last update time (ns since epoch) |
| `exp.since_update()` | Milliseconds since last update |
| `exp.void_time()` | Expiration time (ns since epoch) |
| `exp.ttl()` | Record TTL in seconds |
| `exp.is_tombstone()` | True if tombstone record |
| `exp.digest_modulo(mod)` | Digest modulo (for sampling) |

```python
# TTL < 3600 (expiring within an hour)
exp.lt(exp.ttl(), exp.int_val(3600))

# Record updated within last 24 hours (86400000 ms)
exp.lt(exp.since_update(), exp.int_val(86_400_000))

# Sample ~10% of records
exp.eq(exp.digest_modulo(10), exp.int_val(0))
```

## Pattern Matching

### Regex

```python
# name matches pattern (case insensitive: flags=2)
exp.regex_compare("^alice.*", 2, exp.string_bin("name"))
```

### Geospatial

```python
# point within region
region = '{"type":"AeroCircle","coordinates":[[-122.0, 37.5], 1000]}'
exp.geo_compare(exp.geo_bin("location"), exp.geo_val(region))
```

## Variables and Control Flow

### Conditional (`cond`)

```python
# if age < 18: "minor", elif age < 65: "adult", else: "senior"
exp.cond(
    exp.lt(exp.int_bin("age"), exp.int_val(18)), exp.string_val("minor"),
    exp.lt(exp.int_bin("age"), exp.int_val(65)), exp.string_val("adult"),
    exp.string_val("senior"),
)
```

### Let Bindings (`let_` / `def_` / `var`)

```python
# let total = price * qty in total > 1000
exp.let_(
    exp.def_("total", exp.num_mul(exp.int_bin("price"), exp.int_bin("qty"))),
    exp.gt(exp.var("total"), exp.int_val(1000)),
)
```

## Using with Operations

Expression filters can be applied to any operation via the `filter_expression` policy key.

### Get with Filter

```python
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))
try:
    _, _, bins = client.get(key, policy={"filter_expression": expr})
except aerospike.FilteredOut:
    print("Record does not match filter")
```

### Put with Filter

```python
# Only update if status == "active"
expr = exp.eq(exp.string_bin("status"), exp.string_val("active"))
client.put(key, {"visits": 1}, policy={"filter_expression": expr})
```

### Query with Filter

```python
# Secondary index query + expression filter
query = client.query("test", "demo")
query.where(aerospike.predicates.between("age", 20, 50))

expr = exp.eq(exp.string_bin("region"), exp.string_val("US"))
records = query.results(policy={"filter_expression": expr})
```

### Scan with Filter

```python
# Scan with filter: only active users with TTL > 1 hour
expr = exp.and_(
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
    exp.gt(exp.ttl(), exp.int_val(3600)),
)
scan = client.scan("test", "demo")
records = scan.results(policy={"filter_expression": expr})
```

### Batch with Filter

```python
expr = exp.ge(exp.int_bin("score"), exp.int_val(100))
records = client.get_many(keys, policy={"filter_expression": expr})
```

## Practical Examples

### Active Premium Users

```python
expr = exp.and_(
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
    exp.or_(
        exp.eq(exp.string_bin("tier"), exp.string_val("gold")),
        exp.eq(exp.string_bin("tier"), exp.string_val("platinum")),
    ),
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
)

scan = client.scan("test", "users")
records = scan.results(policy={"filter_expression": expr})
```

### Records Expiring Soon

```python
# Records with TTL < 1 hour
expr = exp.and_(
    exp.gt(exp.ttl(), exp.int_val(0)),       # not immortal
    exp.lt(exp.ttl(), exp.int_val(3600)),     # expiring within 1hr
)
scan = client.scan("test", "cache")
expiring = scan.results(policy={"filter_expression": expr})
```

### High-Value Transactions

```python
# amount * quantity > 10000
expr = exp.gt(
    exp.num_mul(exp.float_bin("amount"), exp.int_bin("quantity")),
    exp.float_val(10000.0),
)
scan = client.scan("test", "transactions")
records = scan.results(policy={"filter_expression": expr})
```
