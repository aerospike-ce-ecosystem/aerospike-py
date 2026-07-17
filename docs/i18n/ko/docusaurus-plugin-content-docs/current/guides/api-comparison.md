---
sidebar_position: 8
title: API Comparison
sidebar_label: API Comparison
slug: /guides/api-comparison
description: Side-by-side API comparison between the official C-based client and aerospike-py.
---

이 문서는 **공식 C 기반 client**(PyPI의 `aerospike`)와 Rust 기반 **aerospike-py**를 비교합니다. 단계별 이전 방법은 [Migration Guide](/docs/guides/migration)를 참고하세요.

## Connection

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create | `aerospike.client(config)` | `aerospike_py.client(config)` | 동일 패턴 |
| Connect | `.connect()` | `.connect()` | 동일; `self` 반환 |
| Connect (auth) | `.connect("user", "pass")` | `.connect("user", "pass")` | 동일 |
| Close | `client.close()` | `client.close()` | 동일 |
| Is connected | `client.is_connected()` | `client.is_connected()` | 동일 |
| Context manager | N/A | `with client: ...` | **aerospike-py 신규** |
| Async client | N/A | `AsyncClient(config)` | **aerospike-py 신규** |

## CRUD Operations

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Put | `client.put(key, bins, meta, policy)` | `client.put(key, bins, meta, policy)` | 동일 |
| Get | `(key, meta, bins) = client.get(key)` | `record = client.get(key)` | `Record` NamedTuple 반환; tuple unpacking 도 동작 |
| Select | `(key, meta, bins) = client.select(key, bins)` | `record = client.select(key, bins)` | `Record` NamedTuple 반환 |
| Exists | `(key, meta) = client.exists(key)` | `result = client.exists(key)` | `ExistsResult` NamedTuple 반환 |
| Remove | `client.remove(key)` | `client.remove(key)` | 동일 |
| Touch | `client.touch(key)` | `client.touch(key, val)` | 동일; `val` 이 새 TTL |
| Append | `client.append(key, bin, val)` | `client.append(key, bin, val)` | 동일 |
| Prepend | `client.prepend(key, bin, val)` | `client.prepend(key, bin, val)` | 동일 |
| Increment | `client.increment(key, bin, offset)` | `client.increment(key, bin, offset)` | 동일 |
| Remove bin | `client.remove_bin(key, bin_names)` | `client.remove_bin(key, bin_names)` | 동일 |
| Operate | `client.operate(key, ops)` | `client.operate(key, ops)` | 동일; `Record` 반환 |
| Operate ordered | `client.operate_ordered(key, ops)` | `client.operate_ordered(key, ops)` | 동일; `OperateOrderedResult` 반환 |

## Batch Operations

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Batch get | `client.get_many(keys)` | `client.batch_read(keys)` | **Method 명 변경**; sync 와 async 둘 다 `LazyBatchRecords` 반환 — materialise 하려면 `.to_dict()` 또는 `.to_numpy(dtype)` 호출 |
| Batch exists | `client.exists_many(keys)` | `client.batch_read(keys, bins=[])` | existence check 용으로 빈 `bins` list |
| Batch select | `client.select_many(keys, bins)` | `client.batch_read(keys, bins=bins)` | `batch_read` 로 통합 |
| Batch operate | `client.batch_operate(keys, ops)` | `client.batch_operate(keys, ops)` | API는 같지만 공식 client는 `aerospike_helpers` 사용 |
| Batch remove | `client.batch_remove(keys)` | `client.batch_remove(keys)` | API는 같지만 공식 client는 `aerospike_helpers` 사용 |
| Batch read (NumPy) | N/A | `client.batch_read(keys).to_numpy(dt)` | **aerospike-py 신규** |
| Batch write (NumPy) | N/A | `client.batch_write_numpy(data, ...)` | **aerospike-py 신규** |

## Query and Scan

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create query | `client.query(ns, set)` | `client.query(ns, set)` | 동일 |
| Query select | `query.select("bin1", "bin2")` | `query.select("bin1", "bin2")` | 동일 |
| Query where | `query.where(predicate)` | `query.where(predicate)` | 동일 |
| Query results | `query.results()` | `query.results()` | 동일 |
| Query foreach | `query.foreach(callback)` | `query.foreach(callback)` | 동일 |
| Scan | `client.scan(ns, set)` | N/A | **Deprecated** — `where()` 없는 `query()` 사용 |

## Secondary Index

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create integer index | `client.index_integer_create(ns, set, bin, name)` | `client.index_integer_create(ns, set, bin, name)` | 동일 |
| Create string index | `client.index_string_create(ns, set, bin, name)` | `client.index_string_create(ns, set, bin, name)` | 동일 |
| Create geo index | `client.index_geo2dsphere_create(ns, set, bin, name)` | `client.index_geo2dsphere_create(ns, set, bin, name)` | 동일 |
| Remove index | `client.index_remove(ns, name)` | `client.index_remove(ns, name)` | 동일 |

## UDF (User-Defined Functions)

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Register UDF | `client.udf_put(filename)` | `client.udf_put(filename)` | 동일 |
| Remove UDF | `client.udf_remove(module)` | `client.udf_remove(module)` | 동일 |
| Apply UDF | `client.apply(key, module, function, args)` | `client.apply(key, module, function, args)` | 동일 |

## Admin (User / Role Management)

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Create user | `client.admin_create_user(user, pw, roles)` | `client.admin_create_user(user, pw, roles)` | 동일 |
| Drop user | `client.admin_drop_user(user)` | `client.admin_drop_user(user)` | 동일 |
| Change password | `client.admin_change_password(user, pw)` | `client.admin_change_password(user, pw)` | 동일 |
| Grant roles | `client.admin_grant_roles(user, roles)` | `client.admin_grant_roles(user, roles)` | 동일 |
| Revoke roles | `client.admin_revoke_roles(user, roles)` | `client.admin_revoke_roles(user, roles)` | 동일 |
| Query user | `client.admin_query_user(user)` | `client.admin_query_user_info(user)` | **Method 명 변경** |
| Query users | `client.admin_query_users()` | `client.admin_query_users_info()` | **Method 명 변경** |
| Create role | `client.admin_create_role(role, privs)` | `client.admin_create_role(role, privs)` | 동일 |
| Drop role | `client.admin_drop_role(role)` | `client.admin_drop_role(role)` | 동일 |
| Grant privileges | `client.admin_grant_privileges(role, privs)` | `client.admin_grant_privileges(role, privs)` | 동일 |
| Revoke privileges | `client.admin_revoke_privileges(role, privs)` | `client.admin_revoke_privileges(role, privs)` | 동일 |
| Set whitelist | N/A | `client.admin_set_whitelist(role, addrs)` | **aerospike-py 신규** |
| Set quotas | N/A | `client.admin_set_quotas(role, r, w)` | **aerospike-py 신규** |

## Info / Cluster

| Operation | Official C Client | aerospike-py | Notes |
|-----------|------------------|--------------|-------|
| Info all nodes | `client.info_all(cmd)` | `client.info_all(cmd)` | 동일; `list[InfoNodeResult]` 반환 |
| Info random node | `client.info_random_node(cmd)` | `client.info_random_node(cmd)` | 동일 |
| Node names | `client.get_node_names()` | `client.get_node_names()` | 동일 |
| Truncate | `client.truncate(ns, set, nanos)` | `client.truncate(ns, set, nanos)` | 동일 |

## Observability

| Feature | Official C Client | aerospike-py |
|---------|------------------|--------------|
| OpenTelemetry tracing | N/A | `init_tracing()` / `shutdown_tracing()` |
| Prometheus metrics | N/A | `start_metrics_server(port)` / `stop_metrics_server()` |
| Log level control | N/A | `set_log_level(level)` |

## CDT Operations

| Module | Official C Client | aerospike-py | Notes |
|--------|------------------|--------------|-------|
| List operations | `aerospike_helpers.operations.list_operations` | `aerospike_py.list_operations` | 37 operation; 동일 의미 |
| Map operations | `aerospike_helpers.operations.map_operations` | `aerospike_py.map_operations` | 33 operation; 동일 의미 |

## Expression Filters

| Feature | Official C Client | aerospike-py | Notes |
|---------|------------------|--------------|-------|
| Expression module | `aerospike_helpers.expressions` | `aerospike_py.exp` | 60+ builder function; 동일 의미 |
| Policy 사용 | `policy["expressions"] = expr.compile()` | `policy["filter_expression"] = expr` | key 명 다름; `.compile()` 불필요 |

## 주요 차이 요약

| Area | Official C Client (`aerospike`) | aerospike-py |
|------|-------------------------------|--------------|
| **Runtime** | C extension (CPython only) | Rust + PyO3 (CPython only) |
| **Return values** | plain tuple | `NamedTuple` (tuple unpacking 도 동작) |
| **Async 지원** | 없음 | `AsyncClient`, 전체 API parity |
| **NumPy 통합** | 없음 | `batch_read(...).to_numpy(dtype)`, `batch_write_numpy` |
| **Observability** | 없음 | OpenTelemetry tracing + Prometheus metrics |
| **Context manager** | 없음 | `with client:` / `async with client:` |
| **Scan** | `client.scan()` | Deprecated; `where()` 없는 `query()` 사용 |
| **Exception 이름** | `TimeoutError`, `IndexError` | `AerospikeTimeoutError`, `AerospikeIndexError` (builtin shadow 방지) |
| **GeoJSON type** | `aerospike.GeoJSON` | 아직 미제공 |
| **Free-threaded Python** | 미지원 | 지원 (3.14t) |
