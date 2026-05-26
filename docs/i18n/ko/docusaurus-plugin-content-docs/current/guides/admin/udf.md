---
title: UDF Guide
sidebar_label: UDF (Lua)
sidebar_position: 2
slug: /guides/udf
description: Register, execute, and remove Lua UDFs on the Aerospike server.
---

User Defined Function (UDF) 은 record 를 소유한 Aerospike server node 위에서 실행되는 Lua 스크립트.

## API

```python
# 등록
client.udf_put("my_udf.lua")

# record 에 대해 실행
result = client.apply(key, "module_name", "function_name", [arg1, arg2])

# 제거
client.udf_remove("module_name")
```

## 예제: Counter UDF

**`counter.lua`**

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

**Python**

```python
client.udf_put("counter.lua")

key = ("test", "demo", "counter1")
result = client.apply(key, "counter", "increment", ["count", 5])  # 5
result = client.apply(key, "counter", "increment", ["count", 3])  # 8

client.udf_remove("counter")
```

**Async**

```python
await client.udf_put("counter.lua")
result = await client.apply(key, "counter", "increment", ["count", 1])
await client.udf_remove("counter")
```

## 비고

- Lua 가 유일한 UDF 언어
- UDF 변경이 모든 node 에 전파되는 데 수 초 소요
- 최선의 성능을 위해 UDF 는 단순하게 유지
