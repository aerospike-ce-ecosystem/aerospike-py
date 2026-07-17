---
title: Getting Started
sidebar_label: Getting Started
sidebar_position: 1
description: Install aerospike-py, connect to a cluster, and read your first record.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

This guide takes you from installation to your first successful read. You need an
Aerospike server or cluster that your machine can already reach. `aerospike-py`
connects to that server; it does not start one for you.

## 1. Install the client

```bash
pip install aerospike-py
```

The package supports CPython 3.10 and later. PyPI provides prebuilt wheels for
supported macOS, Linux, and Windows x64 platforms, so a normal installation does
not require a local Rust or C toolchain.

## 2. Choose a seed address

Start with the host and service port of any reachable node:

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
}
```

Port `3000` is Aerospike's default service port. If your container, Kubernetes
Service, or remote cluster exposes a different address, replace both values with
the address your application can reach.

:::tip[Why only one address?]
A seed is the first node the client contacts. After connecting, the client
discovers the other nodes and keeps the cluster view up to date. Production
configurations can list more than one seed for startup resilience.
:::

## 3. Write and read one record

Choose the API that matches your application. Both clients use the same key,
record, and policy types.

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

Expected output:

```text
{'name': 'Ada', 'active': True}
```

The key has three parts: namespace (`test`), set (`users`), and user key (`ada`).
Aerospike stores the values in named bins. `record.bins` contains those values,
while `record.meta` contains metadata such as generation and TTL.

## 4. Update and clean up

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

## Where to go next

| If you want to… | Read… |
|---|---|
| Set timeouts, pools, and multiple seeds | [Client configuration](guides/config/client-config.md) |
| Understand records and read policies | [Read operations](guides/crud/read.md) |
| Use TTL, generation checks, or batch writes | [Write operations](guides/crud/write.md) |
| Handle failures by exception type | [Error handling](guides/admin/error-handling.md) |
| Run secondary-index queries | [Query and scan](guides/query-scan/query-scan.md) |
| Add the async client to a web service | [FastAPI integration](integrations/fastapi.md) |
| Check every public method and type | [API reference](api/client.md) |
