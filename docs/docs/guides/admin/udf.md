---
title: UDF Guide
sidebar_label: UDF (Lua)
sidebar_position: 2
slug: /guides/udf
description: Register, execute, and remove User Defined Functions (Lua scripts) on the Aerospike server.
---

User Defined Functions (UDFs) are Lua scripts that execute on the Aerospike server.

## Register a UDF

```python
client.udf_put("my_udf.lua")
```

The file must be accessible from the Python process. The UDF is registered on all cluster nodes.

## Execute a UDF on a Record

```python
key = ("test", "demo", "user1")
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
```

| Parameter | Description |
|-----------|-------------|
| `key` | Record key to execute on |
| `module` | UDF module name (without `.lua`) |
| `function` | Function name within the module |
| `args` | Optional list of arguments |

## Remove a UDF

```python
client.udf_remove("my_udf")
```

## Example: Counter UDF

### Lua Script (`counter.lua`)

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
# Register
client.udf_put("counter.lua")

# Execute
key = ("test", "demo", "counter1")
result = client.apply(key, "counter", "increment", ["count", 5])
print(result)  # 5

result = client.apply(key, "counter", "increment", ["count", 3])
print(result)  # 8

# Cleanup
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

- UDFs execute on the server node that owns the record
- Lua is the only supported UDF language
- UDF changes take a few seconds to propagate to all nodes
- Keep UDFs simple for best performance
