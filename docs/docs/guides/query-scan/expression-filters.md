---
title: Expression Filters
sidebar_label: Expression Filters
sidebar_position: 2
slug: /guides/expression-filters
description: Server-side record filtering with 104+ composable expression functions.
---

Server-side filtering during read, write, and query operations. The server evaluates the expression and only returns (or modifies) matching records.

:::note[Server Requirement]
Expression filters require Aerospike Server **5.2+**.
:::

## Import

```python
from aerospike_py import exp
```

## Basic Usage

```python
# Build expression: age >= 21
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Use in any operation via policy
record = client.get(key, policy={"filter_expression": expr})
```

## Value Constructors

| Function | Description |
|----------|-------------|
| `int_val(v)` | 64-bit integer |
| `float_val(v)` | 64-bit float |
| `string_val(v)` | String |
| `bool_val(v)` | Boolean |
| `blob_val(v)` | Bytes |
| `list_val(v)` | List |
| `map_val(v)` | Map/dict |
| `geo_val(v)` | GeoJSON string |
| `nil()` | Nil |
| `infinity()` | Infinity (unbounded ranges) |
| `wildcard()` | Wildcard |

## Bin Accessors

| Function | Description |
|----------|-------------|
| `int_bin(name)` | Integer bin |
| `float_bin(name)` | Float bin |
| `string_bin(name)` | String bin |
| `bool_bin(name)` | Boolean bin |
| `blob_bin(name)` | Blob bin |
| `list_bin(name)` | List bin |
| `map_bin(name)` | Map bin |
| `geo_bin(name)` | Geospatial bin |
| `hll_bin(name)` | HyperLogLog bin |
| `bin_exists(name)` | True if bin exists |
| `bin_type(name)` | Bin particle type |

## Comparison

| Function | Operator |
|----------|----------|
| `eq(l, r)` | `==` |
| `ne(l, r)` | `!=` |
| `gt(l, r)` | `>` |
| `ge(l, r)` | `>=` |
| `lt(l, r)` | `<` |
| `le(l, r)` | `<=` |

## Logic

| Function | Description |
|----------|-------------|
| `and_(*exprs)` | Logical AND |
| `or_(*exprs)` | Logical OR |
| `not_(expr)` | Logical NOT |
| `xor_(*exprs)` | Logical XOR |

```python
# age >= 18 AND active == true
exp.and_(
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
)

# NOT deleted
exp.not_(exp.eq(exp.bool_bin("deleted"), exp.bool_val(True)))
```

## Numeric Operations

| Function | Description |
|----------|-------------|
| `num_add`, `num_sub`, `num_mul`, `num_div` | Arithmetic |
| `num_mod`, `num_pow`, `num_log` | Modulo, power, log |
| `num_abs`, `num_floor`, `num_ceil` | Absolute, floor, ceil |
| `to_int`, `to_float` | Type conversion |
| `min_`, `max_` | Min/max |

```python
# (price * quantity) > 1000
exp.gt(
    exp.num_mul(exp.int_bin("price"), exp.int_bin("quantity")),
    exp.int_val(1000),
)
```

## Record Metadata

| Function | Description |
|----------|-------------|
| `key(exp_type)` | Primary key |
| `key_exists()` | Key stored in metadata? |
| `set_name()` | Set name |
| `record_size()` | Size in bytes (Server 7.0+) |
| `last_update()` | Last update (ns since epoch) |
| `since_update()` | Ms since last update |
| `void_time()` | Expiration (ns since epoch) |
| `ttl()` | TTL in seconds |
| `is_tombstone()` | Tombstone record? |
| `digest_modulo(mod)` | Digest modulo (sampling) |

```python
# Expiring within 1 hour
exp.lt(exp.ttl(), exp.int_val(3600))

# Sample ~10% of records
exp.eq(exp.digest_modulo(10), exp.int_val(0))
```

## Pattern Matching

```python
# Regex (flags=2 for case insensitive)
exp.regex_compare("^alice.*", 2, exp.string_bin("name"))

# Geospatial: point within circle
region = '{"type":"AeroCircle","coordinates":[[-122.0, 37.5], 1000]}'
exp.geo_compare(exp.geo_bin("location"), exp.geo_val(region))
```

## Variables and Control Flow

```python
# Conditional
exp.cond(
    exp.lt(exp.int_bin("age"), exp.int_val(18)), exp.string_val("minor"),
    exp.lt(exp.int_bin("age"), exp.int_val(65)), exp.string_val("adult"),
    exp.string_val("senior"),
)

# Let bindings
exp.let_(
    exp.def_("total", exp.num_mul(exp.int_bin("price"), exp.int_bin("qty"))),
    exp.gt(exp.var("total"), exp.int_val(1000)),
)
```

## Using with Operations

### Get / Put

```python
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Get: raises FilteredOut if no match
record = client.get(key, policy={"filter_expression": expr})

# Put: only update if status == "active"
expr = exp.eq(exp.string_bin("status"), exp.string_val("active"))
client.put(key, {"visits": 1}, policy={"filter_expression": expr})
```

### Query

```python
query = client.query("test", "demo")
query.where(predicates.between("age", 20, 50))

expr = exp.eq(exp.string_bin("region"), exp.string_val("US"))
records = query.results(policy={"filter_expression": expr})
```

### Batch

```python
expr = exp.ge(exp.int_bin("score"), exp.int_val(100))
ops = [{"op": aerospike.OPERATOR_READ, "bin": "score", "val": None}]
records = client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

## Practical Examples

```python
# Active premium users
expr = exp.and_(
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
    exp.or_(
        exp.eq(exp.string_bin("tier"), exp.string_val("gold")),
        exp.eq(exp.string_bin("tier"), exp.string_val("platinum")),
    ),
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
)
records = client.query("test", "users").results(policy={"filter_expression": expr})

# Records expiring within 1 hour
expr = exp.and_(
    exp.gt(exp.ttl(), exp.int_val(0)),
    exp.lt(exp.ttl(), exp.int_val(3600)),
)
expiring = client.query("test", "cache").results(policy={"filter_expression": expr})

# High-value transactions
expr = exp.gt(
    exp.num_mul(exp.float_bin("amount"), exp.int_bin("quantity")),
    exp.float_val(10000.0),
)
records = client.query("test", "transactions").results(policy={"filter_expression": expr})
```
