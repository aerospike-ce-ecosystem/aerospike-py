---
title: Migration from Official Client
sidebar_label: Migration Guide
sidebar_position: 3
slug: /guides/migration
description: Migrate from aerospike-client-python (C-based) to aerospike-py (Rust-based).
---

## Installation

```bash
pip uninstall aerospike
pip install aerospike-py
```

## Import 변경

```python
# Before
import aerospike
from aerospike import exception as ex

# After — drop-in alias
import aerospike_py as aerospike
from aerospike_py import exception as ex
```

## Client 생성

```python
# 동일 API
config = {"hosts": [("127.0.0.1", 3000)]}
client = aerospike.client(config).connect()

# 신규: context manager
with aerospike.client(config).connect() as client:
    pass  # close() 자동 호출
```

## CRUD — 호환

```python
key = ("test", "demo", "user1")

# 동일 signature
client.put(key, {"name": "Alice", "age": 30})
_, meta, bins = client.get(key)
_, meta = client.exists(key)
client.remove(key)
client.select(key, ["name"])
client.touch(key)
client.append(key, "name", " Smith")
client.increment(key, "counter", 1)
```

## Policy, Constants, Exceptions — 호환

```python
# 동일 policy dict
policy = {"socket_timeout": 5000, "total_timeout": 10000, "max_retries": 2}

# 동일 constant
aerospike.POLICY_KEY_SEND       # 1
aerospike.TTL_NEVER_EXPIRE      # -1

# 동일 exception class
from aerospike_py.exception import RecordNotFound, RecordExistsError
```

:::note[Exception Rename]
Python builtin shadow 방지를 위해 `TimeoutError` → `AerospikeTimeoutError`, `IndexError` → `AerospikeIndexError`. 옛 이름은 deprecated alias 로 동작.
:::

## CDT, Expressions, Query — 호환

```python
from aerospike_py import list_operations as lops, map_operations as mops, exp, predicates

# CDT operation
ops = [lops.list_append("tags", "new"), mops.map_put("attrs", "color", "blue")]
client.operate(key, ops)

# Expression filter
expr = exp.ge(exp.int_bin("age"), exp.int_val(18))
client.get(key, policy={"filter_expression": expr})

# Query
query = client.query("test", "demo")
query.where(predicates.between("age", 18, 65))
records = query.results()
```

## Async Client (신규)

공식 client 에 없는 기능:

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

| Feature | Official Client | aerospike-py |
|---------|----------------|--------------|
| Runtime | C extension | Rust + PyO3 |
| Async | 없음 | 있음 |
| NumPy batch read | 없음 | 있음 |
| Context manager | 없음 | 있음 |
| `TimeoutError` | `TimeoutError` | `AerospikeTimeoutError` |
| `IndexError` | `IndexError` | `AerospikeIndexError` |
| `GeoJSON` type | `aerospike.GeoJSON` | 아직 미제공 |
