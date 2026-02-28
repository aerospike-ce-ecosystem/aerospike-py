---
title: 공식 클라이언트에서 마이그레이션
sidebar_label: 마이그레이션 가이드
sidebar_position: 3
slug: /guides/migration
description: aerospike-client-python (C 기반)에서 aerospike-py (Rust 기반)로 마이그레이션하는 방법
---

## 설치

```bash
pip uninstall aerospike
pip install aerospike-py
```

## Import 변경

```python
# 기존
import aerospike
from aerospike import exception as ex

# 변경 후 -- 드롭인 별칭
import aerospike_py as aerospike
from aerospike_py import exception as ex
```

## 클라이언트 생성

```python
# 동일한 API
config = {"hosts": [("127.0.0.1", 3000)]}
client = aerospike.client(config).connect()

# 새 기능: Context Manager
with aerospike.client(config).connect() as client:
    pass  # close()가 자동으로 호출됩니다
```

## CRUD -- 호환

```python
key = ("test", "demo", "user1")

# 동일한 시그니처
client.put(key, {"name": "Alice", "age": 30})
_, meta, bins = client.get(key)
_, meta = client.exists(key)
client.remove(key)
client.select(key, ["name"])
client.touch(key)
client.append(key, "name", " Smith")
client.increment(key, "counter", 1)
```

## 정책, 상수, 예외 -- 호환

```python
# 동일한 정책 딕셔너리
policy = {"socket_timeout": 5000, "total_timeout": 10000, "max_retries": 2}

# 동일한 상수
aerospike.POLICY_KEY_SEND       # 1
aerospike.TTL_NEVER_EXPIRE      # -1

# 동일한 예외 클래스
from aerospike_py.exception import RecordNotFound, RecordExistsError
```

:::note[예외 이름 변경]
`TimeoutError` → `AerospikeTimeoutError`, `IndexError` → `AerospikeIndexError`로 변경되었습니다. Python 내장 예외와의 이름 충돌을 방지하기 위함입니다. 기존 이름은 deprecated 별칭으로 사용 가능합니다.
:::

## CDT, Expression, Query -- 호환

```python
from aerospike_py import list_operations as lops, map_operations as mops, exp, predicates

# CDT 연산
ops = [lops.list_append("tags", "new"), mops.map_put("attrs", "color", "blue")]
client.operate(key, ops)

# Expression 필터
expr = exp.ge(exp.int_bin("age"), exp.int_val(18))
client.get(key, policy={"filter_expression": expr})

# 쿼리
query = client.query("test", "demo")
query.where(predicates.between("age", 18, 65))
records = query.results()
```

## Async Client (신규)

공식 클라이언트에서는 지원하지 않는 기능입니다:

```python
import asyncio
import aerospike_py as aerospike

async def main():
    client = aerospike.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()
    await client.put(key, {"name": "Alice"})
    _, meta, bins = await client.get(key)
    await client.close()

asyncio.run(main())
```

## 알려진 차이점

| 기능 | 공식 클라이언트 | aerospike-py |
|------|----------------|--------------|
| 런타임 | C 확장 모듈 | Rust + PyO3 |
| Async | 미지원 | 지원 |
| NumPy 배치 읽기 | 미지원 | 지원 |
| Context Manager | 미지원 | 지원 |
| `TimeoutError` | `TimeoutError` | `AerospikeTimeoutError` |
| `IndexError` | `IndexError` | `AerospikeIndexError` |
| `GeoJSON` 타입 | `aerospike.GeoJSON` | 아직 미지원 |
