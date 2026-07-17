---
title: UDF Guide
sidebar_label: UDF (Lua)
sidebar_position: 2
slug: /guides/udf
description: Register, execute, and remove Lua UDFs on the Aerospike server.
---

User-Defined Function(UDF)은 Lua 스크립트입니다. Aerospike는 대상 record를 소유한 server node에서 스크립트를 실행합니다.

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

- UDF는 Lua로만 작성할 수 있습니다.
- UDF 변경 사항이 모든 node에 전달되기까지 몇 초가 걸립니다.
- 성능을 위해 UDF는 단순하게 유지하세요.
