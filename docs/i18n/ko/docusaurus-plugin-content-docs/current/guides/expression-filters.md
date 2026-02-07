# Expression Filters

Expression 필터를 사용하면 읽기, 쓰기, 쿼리, 스캔 작업 중에 서버 측에서 record를 필터링할 수 있습니다. 서버가 expression을 평가하고 일치하는 record만 반환(또는 수정)합니다.

:::note[서버 요구 사항]

Expression 필터는 Aerospike Server **5.2+** 이상이 필요합니다.

:::

## Import

```python
from aerospike_py import exp
```

## Overview

Expression은 dict 노드를 반환하는 함수 호출을 조합하여 구성합니다. 이 dict는 `filter_expression` policy 키를 통해 Rust 레이어로 전달되며, Aerospike 와이어 포맷으로 컴파일됩니다.

```python
# Expression 구성: age >= 21
expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# policy에서 사용
policy = {"filter_expression": expr}
_, _, bins = client.get(key, policy=policy)
```

## Value Constructors

리터럴 값 expression을 생성합니다:

| 함수 | 설명 |
|------|------|
| `exp.int_val(val)` | 64비트 정수 |
| `exp.float_val(val)` | 64비트 실수 |
| `exp.string_val(val)` | 문자열 |
| `exp.bool_val(val)` | 불리언 |
| `exp.blob_val(val)` | 바이트 |
| `exp.list_val(val)` | 리스트 |
| `exp.map_val(val)` | Map/dict |
| `exp.geo_val(val)` | GeoJSON 문자열 |
| `exp.nil()` | Nil 값 |
| `exp.infinity()` | 무한대 (범위 제한 없음에 사용) |
| `exp.wildcard()` | 와일드카드 (모든 값과 일치) |

```python
exp.int_val(42)
exp.string_val("hello")
exp.bool_val(True)
exp.list_val([1, 2, 3])
exp.map_val({"key": "value"})
```

## Bin Accessors

타입별로 bin 값을 읽습니다:

| 함수 | 설명 |
|------|------|
| `exp.int_bin(name)` | 정수 bin 읽기 |
| `exp.float_bin(name)` | 실수 bin 읽기 |
| `exp.string_bin(name)` | 문자열 bin 읽기 |
| `exp.bool_bin(name)` | 불리언 bin 읽기 |
| `exp.blob_bin(name)` | blob bin 읽기 |
| `exp.list_bin(name)` | list bin 읽기 |
| `exp.map_bin(name)` | map bin 읽기 |
| `exp.geo_bin(name)` | 지리공간 bin 읽기 |
| `exp.hll_bin(name)` | HyperLogLog bin 읽기 |
| `exp.bin_exists(name)` | bin이 존재하면 True |
| `exp.bin_type(name)` | bin 파티클 타입 |

```python
exp.int_bin("age")
exp.string_bin("name")
exp.bin_exists("optional_field")
```

## Comparison Operations

| 함수 | 설명 |
|------|------|
| `exp.eq(left, right)` | 같음 (`==`) |
| `exp.ne(left, right)` | 같지 않음 (`!=`) |
| `exp.gt(left, right)` | 보다 큼 (`>`) |
| `exp.ge(left, right)` | 크거나 같음 (`>=`) |
| `exp.lt(left, right)` | 보다 작음 (`<`) |
| `exp.le(left, right)` | 작거나 같음 (`<=`) |

```python
# age == 30
exp.eq(exp.int_bin("age"), exp.int_val(30))

# score > 100.5
exp.gt(exp.float_bin("score"), exp.float_val(100.5))

# name != "admin"
exp.ne(exp.string_bin("name"), exp.string_val("admin"))
```

## Logical Operations

| 함수 | 설명 |
|------|------|
| `exp.and_(*exprs)` | 논리 AND |
| `exp.or_(*exprs)` | 논리 OR |
| `exp.not_(expr)` | 논리 NOT |
| `exp.xor_(*exprs)` | 논리 XOR |

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

## Arithmetic Operations

| 함수 | 설명 |
|------|------|
| `exp.num_add(*exprs)` | 덧셈 |
| `exp.num_sub(*exprs)` | 뺄셈 |
| `exp.num_mul(*exprs)` | 곱셈 |
| `exp.num_div(*exprs)` | 나눗셈 |
| `exp.num_mod(num, denom)` | 나머지 |
| `exp.num_pow(base, exponent)` | 거듭제곱 |
| `exp.num_log(num, base)` | 로그 |
| `exp.num_abs(value)` | 절댓값 |
| `exp.num_floor(num)` | 내림 |
| `exp.num_ceil(num)` | 올림 |
| `exp.to_int(num)` | 정수로 변환 |
| `exp.to_float(num)` | 실수로 변환 |
| `exp.min_(*exprs)` | 최솟값 |
| `exp.max_(*exprs)` | 최댓값 |

```python
# (price * quantity) > 1000
exp.gt(
    exp.num_mul(exp.int_bin("price"), exp.int_bin("quantity")),
    exp.int_val(1000),
)
```

## Integer Bitwise Operations

| 함수 | 설명 |
|------|------|
| `exp.int_and(*exprs)` | 비트 AND |
| `exp.int_or(*exprs)` | 비트 OR |
| `exp.int_xor(*exprs)` | 비트 XOR |
| `exp.int_not(expr)` | 비트 NOT |
| `exp.int_lshift(value, shift)` | 왼쪽 시프트 |
| `exp.int_rshift(value, shift)` | 논리 오른쪽 시프트 |
| `exp.int_arshift(value, shift)` | 산술 오른쪽 시프트 |
| `exp.int_count(expr)` | 비트 수 |
| `exp.int_lscan(value, search)` | MSB에서 스캔 |
| `exp.int_rscan(value, search)` | LSB에서 스캔 |

## Record Metadata

| 함수 | 설명 |
|------|------|
| `exp.key(exp_type)` | Record 기본 키 |
| `exp.key_exists()` | 메타데이터에 key가 저장되어 있으면 True |
| `exp.set_name()` | Record set 이름 |
| `exp.record_size()` | Record 크기 (바이트, Server 7.0+) |
| `exp.last_update()` | 마지막 업데이트 시간 (에포크 이후 나노초) |
| `exp.since_update()` | 마지막 업데이트 이후 밀리초 |
| `exp.void_time()` | 만료 시간 (에포크 이후 나노초) |
| `exp.ttl()` | Record TTL (초 단위) |
| `exp.is_tombstone()` | 삭제 표시 record이면 True |
| `exp.digest_modulo(mod)` | 다이제스트 모듈로 (샘플링용) |

```python
# TTL < 3600 (1시간 이내에 만료)
exp.lt(exp.ttl(), exp.int_val(3600))

# 최근 24시간 이내에 업데이트된 record (86400000 ms)
exp.lt(exp.since_update(), exp.int_val(86_400_000))

# record의 약 10% 샘플링
exp.eq(exp.digest_modulo(10), exp.int_val(0))
```

## Pattern Matching

### Regex

```python
# name이 패턴과 일치 (대소문자 무시: flags=2)
exp.regex_compare("^alice.*", 2, exp.string_bin("name"))
```

### Geospatial

```python
# 영역 내의 포인트
region = '{"type":"AeroCircle","coordinates":[[-122.0, 37.5], 1000]}'
exp.geo_compare(exp.geo_bin("location"), exp.geo_val(region))
```

## Variables & Control Flow

### Conditional (cond)

```python
# if age < 18: "minor", elif age < 65: "adult", else: "senior"
exp.cond(
    exp.lt(exp.int_bin("age"), exp.int_val(18)), exp.string_val("minor"),
    exp.lt(exp.int_bin("age"), exp.int_val(65)), exp.string_val("adult"),
    exp.string_val("senior"),
)
```

### Let Binding (let_ / def_ / var)

```python
# let total = price * qty in total > 1000
exp.let_(
    exp.def_("total", exp.num_mul(exp.int_bin("price"), exp.int_bin("qty"))),
    exp.gt(exp.var("total"), exp.int_val(1000)),
)
```

## Usage in Operations

Expression 필터는 `filter_expression` policy 키를 통해 모든 작업에 적용할 수 있습니다.

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
# status == "active"인 경우에만 업데이트
expr = exp.eq(exp.string_bin("status"), exp.string_val("active"))
client.put(key, {"visits": 1}, policy={"filter_expression": expr})
```

### Query with Filter

```python
# 보조 인덱스 쿼리 + expression 필터
query = client.query("test", "demo")
query.where(aerospike.predicates.between("age", 20, 50))

expr = exp.eq(exp.string_bin("region"), exp.string_val("US"))
records = query.results(policy={"filter_expression": expr})
```

### Scan with Filter

```python
# 필터를 적용한 스캔: 활성 사용자 중 TTL > 1시간인 record만
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
ops = [{"op": aerospike.OPERATOR_READ, "bin": "score", "val": None}]
records = client.batch_operate(keys, ops, policy={"filter_expression": expr})
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
# TTL < 1시간인 record
expr = exp.and_(
    exp.gt(exp.ttl(), exp.int_val(0)),       # 영구 보존이 아닌 record
    exp.lt(exp.ttl(), exp.int_val(3600)),     # 1시간 이내에 만료
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
