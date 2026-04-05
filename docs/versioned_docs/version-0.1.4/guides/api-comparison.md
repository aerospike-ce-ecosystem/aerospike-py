---
sidebar_position: 8
title: API Comparison
sidebar_label: API Comparison
slug: /guides/api-comparison
description: Side-by-side API comparison between the official C-based client and aerospike-py.
---

A comprehensive comparison between the **official C-based client** (`aerospike` on PyPI) and **aerospike-py** (Rust-based). For migration steps, see the [Migration Guide](/docs/guides/migration).

## Connection

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create | `aerospike.client(config)` | `aerospike_py.client(config)` | Same pattern |
| Connect | `.connect()` | `.connect()` | Same; returns `self` |
| Connect (auth) | `.connect("user", "pass")` | `.connect("user", "pass")` | Same |
| Close | `client.close()` | `client.close()` | Same |
| Is connected | `client.is_connected()` | `client.is_connected()` | Same |
| Context manager | N/A | `with client: ...` | **New in aerospike-py** |
| Async client | N/A | `AsyncClient(config)` | **New in aerospike-py** |

## CRUD Operations

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Put | `client.put(key, bins, meta, policy)` | `client.put(key, bins, meta, policy)` | Same |
| Get | `(key, meta, bins) = client.get(key)` | `record = client.get(key)` | Returns `Record` NamedTuple; tuple unpacking still works |
| Select | `(key, meta, bins) = client.select(key, bins)` | `record = client.select(key, bins)` | Returns `Record` NamedTuple |
| Exists | `(key, meta) = client.exists(key)` | `result = client.exists(key)` | Returns `ExistsResult` NamedTuple |
| Remove | `client.remove(key)` | `client.remove(key)` | Same |
| Touch | `client.touch(key)` | `client.touch(key, val)` | Same; `val` sets new TTL |
| Append | `client.append(key, bin, val)` | `client.append(key, bin, val)` | Same |
| Prepend | `client.prepend(key, bin, val)` | `client.prepend(key, bin, val)` | Same |
| Increment | `client.increment(key, bin, offset)` | `client.increment(key, bin, offset)` | Same |
| Remove bin | `client.remove_bin(key, bin_names)` | `client.remove_bin(key, bin_names)` | Same |
| Operate | `client.operate(key, ops)` | `client.operate(key, ops)` | Same; returns `Record` |
| Operate ordered | `client.operate_ordered(key, ops)` | `client.operate_ordered(key, ops)` | Same; returns `OperateOrderedResult` |

## Batch Operations

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Batch get | `client.get_many(keys)` | `client.batch_read(keys)` | **Method renamed**; returns `BatchRecords` |
| Batch exists | `client.exists_many(keys)` | `client.batch_read(keys, bins=[])` | Use empty `bins` list for existence check |
| Batch select | `client.select_many(keys, bins)` | `client.batch_read(keys, bins=bins)` | Unified under `batch_read` |
| Batch operate | `client.batch_operate(keys, ops)` | `client.batch_operate(keys, ops)` | Same; official client uses `aerospike_helpers` |
| Batch remove | `client.batch_remove(keys)` | `client.batch_remove(keys)` | Same; official client uses `aerospike_helpers` |
| Batch read (NumPy) | N/A | `client.batch_read(keys, _dtype=dt)` | **New in aerospike-py** |
| Batch write (NumPy) | N/A | `client.batch_write_numpy(data, ...)` | **New in aerospike-py** |

## Query and Scan

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create query | `client.query(ns, set)` | `client.query(ns, set)` | Same |
| Query select | `query.select("bin1", "bin2")` | `query.select("bin1", "bin2")` | Same |
| Query where | `query.where(predicate)` | `query.where(predicate)` | Same |
| Query results | `query.results()` | `query.results()` | Same |
| Query foreach | `query.foreach(callback)` | `query.foreach(callback)` | Same |
| Scan | `client.scan(ns, set)` | N/A | **Deprecated** -- use `query()` without `where()` |

## Secondary Index

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create integer index | `client.index_integer_create(ns, set, bin, name)` | `client.index_integer_create(ns, set, bin, name)` | Same |
| Create string index | `client.index_string_create(ns, set, bin, name)` | `client.index_string_create(ns, set, bin, name)` | Same |
| Create geo index | `client.index_geo2dsphere_create(ns, set, bin, name)` | `client.index_geo2dsphere_create(ns, set, bin, name)` | Same |
| Remove index | `client.index_remove(ns, name)` | `client.index_remove(ns, name)` | Same |

## UDF (User-Defined Functions)

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Register UDF | `client.udf_put(filename)` | `client.udf_put(filename)` | Same |
| Remove UDF | `client.udf_remove(module)` | `client.udf_remove(module)` | Same |
| Apply UDF | `client.apply(key, module, function, args)` | `client.apply(key, module, function, args)` | Same |

## Admin (User / Role Management)

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create user | `client.admin_create_user(user, pw, roles)` | `client.admin_create_user(user, pw, roles)` | Same |
| Drop user | `client.admin_drop_user(user)` | `client.admin_drop_user(user)` | Same |
| Change password | `client.admin_change_password(user, pw)` | `client.admin_change_password(user, pw)` | Same |
| Grant roles | `client.admin_grant_roles(user, roles)` | `client.admin_grant_roles(user, roles)` | Same |
| Revoke roles | `client.admin_revoke_roles(user, roles)` | `client.admin_revoke_roles(user, roles)` | Same |
| Query user | `client.admin_query_user(user)` | `client.admin_query_user_info(user)` | **Method renamed** |
| Query users | `client.admin_query_users()` | `client.admin_query_users_info()` | **Method renamed** |
| Create role | `client.admin_create_role(role, privs)` | `client.admin_create_role(role, privs)` | Same |
| Drop role | `client.admin_drop_role(role)` | `client.admin_drop_role(role)` | Same |
| Grant privileges | `client.admin_grant_privileges(role, privs)` | `client.admin_grant_privileges(role, privs)` | Same |
| Revoke privileges | `client.admin_revoke_privileges(role, privs)` | `client.admin_revoke_privileges(role, privs)` | Same |
| Set whitelist | N/A | `client.admin_set_whitelist(role, addrs)` | **New in aerospike-py** |
| Set quotas | N/A | `client.admin_set_quotas(role, r, w)` | **New in aerospike-py** |

## Info / Cluster

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Info all nodes | `client.info_all(cmd)` | `client.info_all(cmd)` | Same; returns `list[InfoNodeResult]` |
| Info random node | `client.info_random_node(cmd)` | `client.info_random_node(cmd)` | Same |
| Node names | `client.get_node_names()` | `client.get_node_names()` | Same |
| Truncate | `client.truncate(ns, set, nanos)` | `client.truncate(ns, set, nanos)` | Same |

## Observability

| Feature | Official C Client | aerospike-py |
|---------|------------------|--------------|
| OpenTelemetry tracing | N/A | `init_tracing()` / `shutdown_tracing()` |
| Prometheus metrics | N/A | `start_metrics_server(port)` / `stop_metrics_server()` |
| Log level control | N/A | `set_log_level(level)` |

## CDT Operations

| Module | Official C Client | aerospike-py | Notes |
|--------|------------------|--------------|-------|
| List operations | `aerospike_helpers.operations.list_operations` | `aerospike_py.list_operations` | 37 operations; same semantics |
| Map operations | `aerospike_helpers.operations.map_operations` | `aerospike_py.map_operations` | 33 operations; same semantics |

## Expression Filters

| Feature | Official C Client | aerospike-py | Notes |
|---------|------------------|--------------|-------|
| Expression module | `aerospike_helpers.expressions` | `aerospike_py.exp` | 60+ builder functions; same semantics |
| Usage in policies | `policy["expressions"] = expr.compile()` | `policy["filter_expression"] = expr` | Key name differs; no `.compile()` needed |

## Key Differences Summary

| Area | Official C Client (`aerospike`) | aerospike-py |
|------|-------------------------------|--------------|
| **Runtime** | C extension (CPython only) | Rust + PyO3 (CPython only) |
| **Return values** | Plain tuples | `NamedTuple` (tuple unpacking still works) |
| **Async support** | None | `AsyncClient` with full API parity |
| **NumPy integration** | None | `batch_read` with `_dtype`, `batch_write_numpy` |
| **Observability** | None | OpenTelemetry tracing + Prometheus metrics |
| **Context manager** | None | `with client:` / `async with client:` |
| **Scan** | `client.scan()` | Deprecated; use `query()` without `where()` |
| **Exception names** | `TimeoutError`, `IndexError` | `AerospikeTimeoutError`, `AerospikeIndexError` (avoids shadowing builtins) |
| **GeoJSON type** | `aerospike.GeoJSON` | Not yet available |
| **Free-threaded Python** | Not supported | Supported (3.14t) |
