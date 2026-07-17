---
title: Getting Started
sidebar_label: Getting Started
sidebar_position: 1
description: Install aerospike-py and connect to an Aerospike cluster in minutes.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Installation

```bash
pip install aerospike-py
```

**Requirements:** Python 3.10+ (CPython)

소스 checkout에서 작업한다면 `make run-aerospike-ce`를 실행해 로컬 Aerospike CE 컨테이너를 시작하세요. 컨테이너는 `127.0.0.1:18710`에서 요청을 받습니다. Aerospike를 기본 service port로 직접 실행했다면 아래 예제의 `18710`을 `3000`으로 바꾸세요.

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
import aerospike_py as aerospike
from aerospike_py import Record

with aerospike.client({
    "hosts": [("127.0.0.1", 18710)],
}).connect() as client:
    key: tuple[str, str, str] = ("test", "demo", "user1")

    # Write
    client.put(key, {"name": "Alice", "age": 30})

    # Read
    record: Record = client.get(key)
    print(record.bins)       # {"name": "Alice", "age": 30}
    print(record.meta.gen)   # 1

    # Update
    client.increment(key, "age", 1)

    # Delete
    client.remove(key)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
import asyncio
import aerospike_py as aerospike
from aerospike_py import AsyncClient, Record

async def main() -> None:
    async with AsyncClient({"hosts": [("127.0.0.1", 18710)]}) as client:
        await client.connect()
        key: tuple[str, str, str] = ("test", "demo", "user1")

        await client.put(key, {"name": "Bob", "age": 25})

        record: Record = await client.get(key)
        print(record.bins)  # {"name": "Bob", "age": 25}

        # Concurrent writes
        keys = [("test", "demo", f"item_{i}") for i in range(10)]
        await asyncio.gather(*(client.put(k, {"idx": i}) for i, k in enumerate(keys)))

        await client.remove(key)

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Policy 와 Metadata

```python
import aerospike_py as aerospike

key = ("test", "demo", "user1")

# TTL (초)
client.put(key, {"val": 1}, meta={"ttl": 300})

# Create only (이미 존재하면 실패)
client.put(key, {"val": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# Optimistic locking
record = client.get(key)
client.put(
    key,
    {"val": record.bins["val"] + 1},
    meta={"gen": record.meta.gen},
    policy={"gen": aerospike.POLICY_GEN_EQ},
)
```

## 다음 단계

| Topic | 설명 |
|-------|-------------|
| [Read Operations](guides/crud/read.md) | get, select, exists, batch read |
| [Write Operations](guides/crud/write.md) | put, update, delete, operate, batch operate |
| [CDT Operations](guides/crud/operations.md) | atomic list 와 map operation |
| [NumPy Batch](guides/crud/numpy-batch.md) | zero-copy columnar batch read |
| [Query](guides/query-scan/query-scan.md) | secondary index 기반 query |
| [Expression Filters](guides/query-scan/expression-filters.md) | server-side filtering |
| [Configuration](guides/config/client-config.md) | connection, pool, timeout |
| [API Reference](api/client.md) | 전체 method signature |
| [Types](api/types.md) | NamedTuple / TypedDict 정의 |
