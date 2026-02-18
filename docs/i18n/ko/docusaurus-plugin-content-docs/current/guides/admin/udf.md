---
title: UDF Guide
sidebar_label: UDF (Lua)
sidebar_position: 2
slug: /guides/udf
description: Aerospike 서버에서 Lua UDF 등록, 실행, 제거 가이드
---

UDF (User Defined Functions)는 Aerospike 서버에서 실행되는 Lua 스크립트입니다.

## Register UDF

```python
client.udf_put("my_udf.lua")
```

파일은 Python 프로세스에서 접근 가능해야 합니다. UDF는 모든 클러스터 노드에 등록됩니다.

## Execute UDF on Record

```python
key = ("test", "demo", "user1")
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
```

| 매개변수 | 설명 |
|----------|------|
| `key` | 실행 대상 record 키 |
| `module` | UDF 모듈 이름 (`.lua` 제외) |
| `function` | 모듈 내 함수 이름 |
| `args` | 선택적 인수 리스트 |

## Remove UDF

```python
client.udf_remove("my_udf")
```

## Example: Counter UDF

### Lua Script (counter.lua)

```lua
function increment(rec, bin_name, amount)
    if aerospike:exists(rec) then
        rec[bin_name] = rec[bin_name] + amount
        aerospike:update(rec)
    else
        rec[bin_name] = amount
        aerospike:create(rec)
    end
    return rec[bin_name]
end
```

### Python Usage

```python
# 등록
client.udf_put("counter.lua")

# 실행
key = ("test", "demo", "counter1")
result = client.apply(key, "counter", "increment", ["count", 5])
print(result)  # 5

result = client.apply(key, "counter", "increment", ["count", 3])
print(result)  # 8

# 정리
client.udf_remove("counter")
```

## Async UDF

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

    await client.udf_put("counter.lua")

    key = ("test", "demo", "counter1")
    result = await client.apply(key, "counter", "increment", ["count", 1])
    print(result)

    await client.udf_remove("counter")
    await client.close()

asyncio.run(main())
```

## Notes

- UDF는 해당 record를 소유한 서버 노드에서 실행됩니다
- Lua만 UDF 언어로 지원됩니다
- UDF 변경 사항이 모든 노드에 전파되는 데 몇 초가 걸립니다
- 최적의 성능을 위해 UDF를 간결하게 유지하세요
