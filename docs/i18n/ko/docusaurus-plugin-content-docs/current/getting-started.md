---
title: Getting Started
sidebar_label: 시작하기
sidebar_position: 1
description: aerospike-py 설치 및 Aerospike 클러스터 연결 가이드
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Prerequisites

- **Python 3.10+**

### Supported Platforms

| OS | Architecture |
|---|---|
| Linux | x86_64, aarch64 |
| macOS | x86_64, aarch64 (Apple Silicon) |
| Windows | x64 |

## Installation

```bash
pip install aerospike-py
```

설치 확인:

```bash
python -c "import aerospike_py as aerospike; print(aerospike.__version__)"
```

:::tip[Install from Source]

개발 빌드나 기여를 위해서는 [Contributing Guide](contributing.md)를 참조하세요.

:::

## Quick Start

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

# 생성 및 연결 (Context Manager 사용)
with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    # 레코드 쓰기
    key = ("test", "demo", "user1")
    client.put(key, {"name": "Alice", "age": 30})

    # 레코드 읽기
    _, meta, bins = client.get(key)
    print(f"bins={bins}, gen={meta['gen']}, ttl={meta['ttl']}")

    # 증분 업데이트
    client.increment(key, "age", 1)

    # 원자적 다중 연산
    ops = [
        {"op": aerospike.OPERATOR_INCR, "bin": "age", "val": 1},
        {"op": aerospike.OPERATOR_READ, "bin": "age", "val": None},
    ]
    _, _, bins = client.operate(key, ops)

    # 삭제
    client.remove(key)
# client.close()가 자동으로 호출됩니다
```

:::tip[Context Manager 없이 사용]

`connect()` / `close()`를 수동으로 호출할 수도 있습니다:

```python
client = aerospike.client({...}).connect()
# ... 작업 수행 ...
client.close()
```

:::

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
import aerospike_py as aerospike
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

    # 레코드 쓰기
    key = ("test", "demo", "user1")
    await client.put(key, {"name": "Bob", "age": 25})

    # 레코드 읽기
    _, meta, bins = await client.get(key)
    print(f"bins={bins}, gen={meta['gen']}, ttl={meta['ttl']}")

    # 증분 업데이트
    await client.increment(key, "age", 1)

    # 원자적 다중 연산
    ops = [
        {"op": aerospike.OPERATOR_INCR, "bin": "age", "val": 1},
        {"op": aerospike.OPERATOR_READ, "bin": "age", "val": None},
    ]
    _, _, bins = await client.operate(key, ops)

    # asyncio.gather를 사용한 동시 쓰기
    keys = [("test", "demo", f"item_{i}") for i in range(10)]
    tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
    await asyncio.gather(*tasks)

    # 삭제
    await client.remove(key)

    await client.close()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Configuration

`config` 딕셔너리가 지원하는 옵션:

| 키 | 타입 | 설명 |
|-----|------|-------------|
| `hosts` | `list[tuple[str, int]]` | 시드 호스트 주소 |
| `cluster_name` | `str` | 예상 클러스터 이름 (선택) |
| `timeout` | `int` | 연결 타임아웃 (ms, 기본값: 1000) |
| `auth_mode` | `int` | `AUTH_INTERNAL`, `AUTH_EXTERNAL`, 또는 `AUTH_PKI` |

## Policies & Metadata

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# TTL 설정하여 쓰기 (초 단위)
client.put(key, {"val": 1}, meta={"ttl": 300})

# 키 전송 정책으로 쓰기
client.put(key, {"val": 1}, policy={"key": aerospike.POLICY_KEY_SEND})

# 생성 전용 (이미 존재하면 실패)
client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# 세대 검사를 통한 Optimistic Locking
_, meta, bins = client.get(key)
client.put(key, {"val": bins["val"] + 1},
           meta={"gen": meta["gen"]},
           policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
# TTL 설정하여 쓰기 (초 단위)
await client.put(key, {"val": 1}, meta={"ttl": 300})

# 키 전송 정책으로 쓰기
await client.put(key, {"val": 1}, policy={"key": aerospike.POLICY_KEY_SEND})

# 생성 전용 (이미 존재하면 실패)
await client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})

# 세대 검사를 통한 Optimistic Locking
_, meta, bins = await client.get(key)
await client.put(key, {"val": bins["val"] + 1},
                 meta={"gen": meta["gen"]},
                 policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
</Tabs>

## Next Steps

- [CRUD & Batch Guide](guides/crud.md) - CRUD 및 배치 작업
- [Query & Scan Guide](guides/query-scan.md) - Secondary Index 쿼리와 스캔
- [Expression Filters Guide](guides/expression-filters.md) - 서버사이드 필터링
- [List CDT Operations Guide](guides/cdt-list.md) - 원자적 리스트 연산
- [Map CDT Operations Guide](guides/cdt-map.md) - 원자적 맵 연산
- [API Reference](api/client.md) - 전체 API 문서
