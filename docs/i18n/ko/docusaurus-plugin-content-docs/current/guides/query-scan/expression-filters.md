---
title: Expression 필터
sidebar_label: Expression 필터
sidebar_position: 2
slug: /guides/expression-filters
description: 조합 가능한 104개 이상의 expression 함수로 서버에서 Record를 필터링하는 방법
---

Expression filter는 read, write, query operation에 적용할 수 있습니다. Server가 expression을 평가해 조건에 맞는 record만 반환하거나 수정합니다.

:::note[서버 요구사항]
Expression filter를 사용하려면 Aerospike Server **5.2 이상**이 필요합니다.
:::

## Import

```python
from aerospike_py import exp, predicates
```

## 기본 사용

```python
# 표현식 빌드: age >= 21
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# policy 통해 어떤 operation 에서든 사용
record = client.get(key, policy={"filter_expression": expr})
```

## Value Constructor

| Function | 설명 |
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
| `infinity()` | Infinity (unbounded range) |
| `wildcard()` | Wildcard |

## Bin Accessor

| Function | 설명 |
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
| `bin_exists(name)` | bin 존재 시 True |
| `bin_type(name)` | bin particle type |

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

| Function | 설명 |
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

## 수치 연산

| Function | 설명 |
|----------|-------------|
| `num_add`, `num_sub`, `num_mul`, `num_div` | 산술 |
| `num_mod`, `num_pow`, `num_log` | modulo, power, log |
| `num_abs`, `num_floor`, `num_ceil` | absolute, floor, ceil |
| `to_int`, `to_float` | 타입 변환 |
| `min_`, `max_` | min/max |

```python
# (price * quantity) > 1000
exp.gt(
    exp.num_mul(exp.int_bin("price"), exp.int_bin("quantity")),
    exp.int_val(1000),
)
```

## Record Metadata

| Function | 설명 |
|----------|-------------|
| `key(exp_type)` | primary key |
| `key_exists()` | metadata 에 key 저장되어 있는가? |
| `set_name()` | set 이름 |
| `record_size()` | 바이트 크기 (Server 7.0+) |
| `last_update()` | 마지막 update (epoch 부터 ns) |
| `since_update()` | 마지막 update 부터 ms |
| `void_time()` | expiration (epoch 부터 ns) |
| `ttl()` | TTL 초 |
| `is_tombstone()` | tombstone record? |
| `digest_modulo(mod)` | digest modulo (sampling) |

```python
# 1시간 내 만료
exp.lt(exp.ttl(), exp.int_val(3600))

# record 의 ~10% sample
exp.eq(exp.digest_modulo(10), exp.int_val(0))
```

## Pattern Matching

```python
# Regex (flags=2 는 case insensitive)
exp.regex_compare("^alice.*", 2, exp.string_bin("name"))

# Geospatial: 원 안의 point
region = '{"type":"AeroCircle","coordinates":[[-122.0, 37.5], 1000]}'
exp.geo_compare(exp.geo_bin("location"), exp.geo_val(region))
```

## 변수와 제어 흐름

```python
# Conditional
exp.cond(
    exp.lt(exp.int_bin("age"), exp.int_val(18)), exp.string_val("minor"),
    exp.lt(exp.int_bin("age"), exp.int_val(65)), exp.string_val("adult"),
    exp.string_val("senior"),
)

# Let binding
exp.let_(
    exp.def_("total", exp.num_mul(exp.int_bin("price"), exp.int_bin("qty"))),
    exp.gt(exp.var("total"), exp.int_val(1000)),
)
```

## Operation 과 함께 사용

### Get / Put

```python
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Get: 매칭 없으면 FilteredOut raise
record = client.get(key, policy={"filter_expression": expr})

# Put: status == "active" 일 때만 update
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

## Integer Bitwise Operation

| Function | 설명 |
|----------|-------------|
| `int_and(*exprs)` | Bitwise AND |
| `int_or(*exprs)` | Bitwise OR |
| `int_xor(*exprs)` | Bitwise XOR |
| `int_not(expr)` | Bitwise NOT |
| `int_lshift(value, shift)` | Left shift |
| `int_rshift(value, shift)` | Logical right shift |
| `int_arshift(value, shift)` | Arithmetic right shift |
| `int_count(expr)` | bit count (popcount) |
| `int_lscan(value, search)` | MSB 부터 scan |
| `int_rscan(value, search)` | LSB 부터 scan |

```python
# flags 의 bit 3 가 set 되어 있는가
exp.ne(
    exp.int_and(exp.int_bin("flags"), exp.int_val(0x08)),
    exp.int_val(0),
)

# permissions 를 왼쪽으로 4 bit shift
exp.int_lshift(exp.int_bin("perms"), exp.int_val(4))
```

## Type Constants

`key()` 와 `bin_type()` 과 함께 `EXP_TYPE_*` constant 사용:

| Constant | Value | 설명 |
|----------|-------|-------------|
| `exp.EXP_TYPE_NIL` | 0 | Nil |
| `exp.EXP_TYPE_BOOL` | 1 | Boolean |
| `exp.EXP_TYPE_INT` | 2 | Integer |
| `exp.EXP_TYPE_STRING` | 3 | String |
| `exp.EXP_TYPE_LIST` | 4 | List |
| `exp.EXP_TYPE_MAP` | 5 | Map |
| `exp.EXP_TYPE_BLOB` | 6 | Blob (bytes) |
| `exp.EXP_TYPE_FLOAT` | 7 | Float |
| `exp.EXP_TYPE_GEO` | 8 | GeoJSON |
| `exp.EXP_TYPE_HLL` | 9 | HyperLogLog |

```python
# integer primary key 가져오기
exp.key(exp.EXP_TYPE_INT)

# "data" bin 이 list 인 record 필터
exp.eq(exp.bin_type("data"), exp.int_val(exp.EXP_TYPE_LIST))
```

## 실용 예제

```python
# active premium user
expr = exp.and_(
    exp.eq(exp.bool_bin("active"), exp.bool_val(True)),
    exp.or_(
        exp.eq(exp.string_bin("tier"), exp.string_val("gold")),
        exp.eq(exp.string_bin("tier"), exp.string_val("platinum")),
    ),
    exp.ge(exp.int_bin("age"), exp.int_val(18)),
)
records = client.query("test", "users").results(policy={"filter_expression": expr})

# 1시간 내 만료되는 record
expr = exp.and_(
    exp.gt(exp.ttl(), exp.int_val(0)),
    exp.lt(exp.ttl(), exp.int_val(3600)),
)
expiring = client.query("test", "cache").results(policy={"filter_expression": expr})

# 고액 transaction
expr = exp.gt(
    exp.num_mul(exp.float_bin("amount"), exp.int_bin("quantity")),
    exp.float_val(10000.0),
)
records = client.query("test", "transactions").results(policy={"filter_expression": expr})
```
