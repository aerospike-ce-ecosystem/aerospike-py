---
name: api-query-expressions
description: aerospike-py query, secondary index, predicates, and expression filters for server-side filtering
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## Query (Sync/Async 모두 지원)

```python
from aerospike_py import predicates as p

# 인덱스 먼저 생성
client.index_integer_create("test", "demo", "age", "age_idx")

# Sync
query: Query = client.query("test", "demo")
query.select("name", "age")             # 특정 bin 선택
query.where(p.between("age", 20, 40))   # 필터 설정
records: list[Record] = query.results()  # 실행

# foreach (콜백, return False로 조기 중단)
def process(record: Record) -> bool | None:
    print(record.bins)
    return None  # continue (return False to stop)
query.foreach(process)

# Async
query: AsyncQuery = client.query("test", "demo")
query.select("name", "age")
query.where(p.between("age", 20, 40))
records: list[Record] = await query.results()
await query.foreach(process)

# Predicates:
# p.equals(bin_name, val)
# p.between(bin_name, min_val, max_val)
# p.contains(bin_name, index_type, val)  # collection index
# p.geo_within_geojson_region(bin_name, geojson)  # 미지원
# p.geo_within_radius(bin_name, lat, lng, radius)  # 미지원
# p.geo_contains_geojson_point(bin_name, geojson)  # 미지원
```

## Expression 필터

서버 사이드 필터링 (Aerospike 5.2+). 인덱스 불필요.

```python
from aerospike_py import exp

# 단순 비교
expr = exp.gt(exp.int_bin("age"), exp.int_val(21))
record = client.get(key, policy={"expressions": expr})

# 복합 조건 (AND/OR)
expr = exp.and_(
    exp.gt(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.string_bin("status"), exp.string_val("active")),
)

# 레코드 메타데이터
expr = exp.gt(exp.ttl(), exp.int_val(3600))  # TTL > 1시간
expr = exp.eq(exp.set_name(), exp.string_val("demo"))

# bin 존재 여부
expr = exp.bin_exists("optional_field")

# 정규식
expr = exp.regex_compare("^user_", 0, exp.string_bin("name"))

# 변수 바인딩
expr = exp.let_(
    exp.def_("x", exp.int_bin("a")),
    exp.gt(exp.var("x"), exp.int_val(10)),
)

# 조건 분기
expr = exp.cond(
    exp.gt(exp.int_bin("score"), exp.int_val(90)), exp.string_val("A"),
    exp.gt(exp.int_bin("score"), exp.int_val(80)), exp.string_val("B"),
    exp.string_val("C"),  # default
)

# policy에서 사용
record = client.get(key, policy={"expressions": expr})
batch = client.batch_read(keys, policy={"filter_expression": expr})
query.results(policy={"expressions": expr})
```

### Expression 빌더 함수 목록

| 카테고리 | 함수 |
|----------|------|
| 값 | `int_val`, `float_val`, `string_val`, `bool_val`, `blob_val`, `list_val`, `map_val`, `geo_val`, `nil`, `infinity`, `wildcard` |
| Bin | `int_bin`, `float_bin`, `string_bin`, `bool_bin`, `blob_bin`, `list_bin`, `map_bin`, `geo_bin`, `hll_bin`, `bin_exists`, `bin_type` |
| 비교 | `eq`, `ne`, `gt`, `ge`, `lt`, `le` |
| 논리 | `and_`, `or_`, `not_`, `xor_` |
| 메타 | `key`, `key_exists`, `set_name`, `record_size`, `last_update`, `since_update`, `void_time`, `ttl`, `is_tombstone`, `digest_modulo` |
| 수치 | `num_add`, `num_sub`, `num_mul`, `num_div`, `num_mod`, `num_pow`, `num_log`, `num_abs`, `num_floor`, `num_ceil`, `to_int`, `to_float`, `min_`, `max_` |
| 비트 | `int_and`, `int_or`, `int_xor`, `int_not`, `int_lshift`, `int_rshift`, `int_arshift`, `int_count`, `int_lscan`, `int_rscan` |
| 패턴 | `regex_compare`, `geo_compare` |
| 제어 | `cond`, `var`, `def_`, `let_` |

## Index

```python
client.index_integer_create("test", "demo", "age", "age_idx")
client.index_string_create("test", "demo", "name", "name_idx")
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
client.index_remove("test", "age_idx")

# Async
await client.index_integer_create("test", "demo", "age", "age_idx")
await client.index_remove("test", "age_idx")
```

### Index 상수

```python
INDEX_NUMERIC, INDEX_STRING, INDEX_BLOB, INDEX_GEO2DSPHERE
INDEX_TYPE_DEFAULT, INDEX_TYPE_LIST, INDEX_TYPE_MAPKEYS, INDEX_TYPE_MAPVALUES
```
