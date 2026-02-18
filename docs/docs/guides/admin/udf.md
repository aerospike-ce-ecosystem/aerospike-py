---
title: UDF Guide
sidebar_label: UDF (Lua)
sidebar_position: 2
slug: /guides/udf
description: Register, execute, and remove Lua UDFs on the Aerospike server.
---

User Defined Functions (UDFs) are Lua scripts that execute on the Aerospike server node owning the record.

## API

```python
# Register
client.udf_put("my_udf.lua")

# Execute on a record
result = client.apply(key, "module_name", "function_name", [arg1, arg2])

# Remove
client.udf_remove("module_name")
```

## Example: Counter UDF

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

## Notes

- Lua is the only supported UDF language
- UDF changes take a few seconds to propagate to all nodes
- Keep UDFs simple for best performance
