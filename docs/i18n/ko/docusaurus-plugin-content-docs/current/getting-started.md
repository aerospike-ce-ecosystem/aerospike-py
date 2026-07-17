---
title: 시작하기
sidebar_label: 시작하기
sidebar_position: 1
description: aerospike-py를 설치하고 cluster에 연결해 첫 record를 조회합니다.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

이 문서는 설치부터 첫 record 조회까지 안내합니다. 먼저 현재 machine에서 접근할 수
있는 Aerospike server 또는 cluster가 필요합니다. `aerospike-py`는 실행 중인
server에 연결하는 client이며 server를 함께 시작하지 않습니다.

## 1. Client 설치

```bash
pip install aerospike-py
```

CPython 3.10 이상을 지원합니다. 지원하는 macOS, Linux, Windows x64 환경에서는
PyPI가 prebuilt wheel을 제공하므로, 일반적인 설치 과정에 로컬 Rust 또는 C
toolchain이 필요하지 않습니다.

## 2. Seed address 설정

접근할 수 있는 node 하나의 host와 service port로 시작합니다.

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
}
```

`3000`은 Aerospike의 기본 service port입니다. Container, Kubernetes Service,
remote cluster가 다른 address를 노출한다면 두 값을 application에서 접근할 수
있는 address로 바꾸세요.

:::tip[Address가 하나만 있어도 되는 이유]
Seed는 client가 처음 연결하는 node입니다. 연결이 끝나면 client가 나머지 node를
찾고 cluster 정보를 계속 갱신합니다. Production 환경에서는 시작 시 가용성을 높이기
위해 seed를 여러 개 지정할 수 있습니다.
:::

## 3. 첫 record 쓰기와 읽기

Application에 맞는 API를 선택하세요. Sync와 async client는 같은 key, record,
policy type을 사용합니다.

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
from aerospike_py import Client

config = {"hosts": [("127.0.0.1", 3000)]}
key = ("test", "users", "ada")

with Client(config).connect() as client:
    client.put(key, {"name": "Ada", "active": True})
    record = client.get(key)
    print(record.bins)
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
import asyncio
from aerospike_py import AsyncClient

config = {"hosts": [("127.0.0.1", 3000)]}
key = ("test", "users", "ada")

async def main() -> None:
    async with AsyncClient(config) as client:
        await client.connect()
        await client.put(key, {"name": "Ada", "active": True})
        record = await client.get(key)
        print(record.bins)

asyncio.run(main())
```

  </TabItem>
</Tabs>

예상 출력:

```text
{'name': 'Ada', 'active': True}
```

Key는 namespace(`test`), set(`users`), user key(`ada`)로 구성됩니다. Aerospike는
값을 이름이 있는 bin에 저장합니다. `record.bins`에는 bin 값이, `record.meta`에는
generation과 TTL 같은 metadata가 들어 있습니다.

## 4. Update와 정리

<Tabs>
  <TabItem value="sync-update" label="Sync" default>

```python
with Client(config).connect() as client:
    client.increment(key, "login_count", 1)
    updated = client.get(key)
    print(updated.bins)
    client.remove(key)
```

  </TabItem>
  <TabItem value="async-update" label="Async">

```python
async with AsyncClient(config) as client:
    await client.connect()
    await client.increment(key, "login_count", 1)
    updated = await client.get(key)
    print(updated.bins)
    await client.remove(key)
```

  </TabItem>
</Tabs>

## 다음 문서

| 필요한 작업 | 참고 문서 |
|---|---|
| Timeout, connection pool, 여러 seed 설정 | [Client configuration](guides/config/client-config.md) |
| Record와 read policy 이해 | [Read operations](guides/crud/read.md) |
| TTL, generation check, batch write 사용 | [Write operations](guides/crud/write.md) |
| Exception type별 오류 처리 | [Error handling](guides/admin/error-handling.md) |
| Secondary index query 실행 | [Query and scan](guides/query-scan/query-scan.md) |
| Web service에 async client 연결 | [FastAPI integration](integrations/fastapi.md) |
| Public method와 type 확인 | [API reference](api/client.md) |
