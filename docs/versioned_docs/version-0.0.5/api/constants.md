---
title: Constants
sidebar_label: Constants
sidebar_position: 4
description: All constants used across the aerospike-py API.
---

```python
import aerospike_py as aerospike
```

## Policy

### Key

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_KEY_DIGEST` | 0 | Store only the digest (default) |
| `POLICY_KEY_SEND` | 1 | Send and store the key |

### Exists

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_EXISTS_IGNORE` | 0 | Write regardless (default) |
| `POLICY_EXISTS_UPDATE` | 1 | Update existing |
| `POLICY_EXISTS_UPDATE_ONLY` | 2 | Fail if not exists |
| `POLICY_EXISTS_REPLACE` | 3 | Replace all bins |
| `POLICY_EXISTS_REPLACE_ONLY` | 4 | Replace only if exists |
| `POLICY_EXISTS_CREATE_ONLY` | 5 | Fail if exists |

### Generation

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_GEN_IGNORE` | 0 | Ignore generation (default) |
| `POLICY_GEN_EQ` | 1 | Write only if gen matches |
| `POLICY_GEN_GT` | 2 | Write only if gen is greater |

### Replica

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_REPLICA_MASTER` | 0 | Read from master |
| `POLICY_REPLICA_SEQUENCE` | 1 | Round-robin (default) |
| `POLICY_REPLICA_PREFER_RACK` | 2 | Prefer rack-local |

### Commit Level

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_COMMIT_LEVEL_ALL` | 0 | Wait for all replicas |
| `POLICY_COMMIT_LEVEL_MASTER` | 1 | Master only |

### Read Mode AP

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_READ_MODE_AP_ONE` | 0 | Read from one node |
| `POLICY_READ_MODE_AP_ALL` | 1 | Read from all nodes |

## TTL

| Constant | Value | Description |
|----------|-------|-------------|
| `TTL_NAMESPACE_DEFAULT` | 0 | Use namespace default |
| `TTL_NEVER_EXPIRE` | -1 | Never expire |
| `TTL_DONT_UPDATE` | -2 | Don't update TTL on write |
| `TTL_CLIENT_DEFAULT` | -3 | Use client default |

## Auth Mode

| Constant | Value | Description |
|----------|-------|-------------|
| `AUTH_INTERNAL` | 0 | Internal authentication |
| `AUTH_EXTERNAL` | 1 | External (LDAP) |
| `AUTH_PKI` | 2 | PKI authentication |

## Operators

Used with `operate()` and `batch_operate()`.

| Constant | Value | Description |
|----------|-------|-------------|
| `OPERATOR_READ` | 1 | Read a bin |
| `OPERATOR_WRITE` | 2 | Write a bin |
| `OPERATOR_INCR` | 5 | Increment int/float bin |
| `OPERATOR_APPEND` | 9 | Append to string bin |
| `OPERATOR_PREPEND` | 10 | Prepend to string bin |
| `OPERATOR_TOUCH` | 11 | Reset record TTL |
| `OPERATOR_DELETE` | 14 | Delete the record |

## Index Type

| Constant | Value | Description |
|----------|-------|-------------|
| `INDEX_NUMERIC` | 0 | Numeric |
| `INDEX_STRING` | 1 | String |
| `INDEX_BLOB` | 2 | Blob |
| `INDEX_GEO2DSPHERE` | 3 | Geospatial |

## Index Collection Type

| Constant | Value | Description |
|----------|-------|-------------|
| `INDEX_TYPE_DEFAULT` | 0 | Scalar (default) |
| `INDEX_TYPE_LIST` | 1 | List elements |
| `INDEX_TYPE_MAPKEYS` | 2 | Map keys |
| `INDEX_TYPE_MAPVALUES` | 3 | Map values |

## Log Level

| Constant | Value | Description |
|----------|-------|-------------|
| `LOG_LEVEL_OFF` | -1 | Disabled |
| `LOG_LEVEL_ERROR` | 0 | Error only |
| `LOG_LEVEL_WARN` | 1 | Warnings+ |
| `LOG_LEVEL_INFO` | 2 | Info+ |
| `LOG_LEVEL_DEBUG` | 3 | Debug+ |
| `LOG_LEVEL_TRACE` | 4 | All |

## Serializer

| Constant | Value | Description |
|----------|-------|-------------|
| `SERIALIZER_NONE` | 0 | No serialization |
| `SERIALIZER_PYTHON` | 1 | Python pickle |
| `SERIALIZER_USER` | 2 | User-defined |

## List CDT

### Return Type

| Constant | Description |
|----------|-------------|
| `LIST_RETURN_NONE` | No return |
| `LIST_RETURN_INDEX` | Index |
| `LIST_RETURN_REVERSE_INDEX` | Reverse index |
| `LIST_RETURN_RANK` | Rank |
| `LIST_RETURN_REVERSE_RANK` | Reverse rank |
| `LIST_RETURN_COUNT` | Count |
| `LIST_RETURN_VALUE` | Value |
| `LIST_RETURN_EXISTS` | Boolean |

### Order

| Constant | Description |
|----------|-------------|
| `LIST_UNORDERED` | Unordered (default) |
| `LIST_ORDERED` | Ordered |

### Sort Flags

| Constant | Description |
|----------|-------------|
| `LIST_SORT_DEFAULT` | Default sort |
| `LIST_SORT_DROP_DUPLICATES` | Drop duplicates |

### Write Flags

| Constant | Description |
|----------|-------------|
| `LIST_WRITE_DEFAULT` | Default |
| `LIST_WRITE_ADD_UNIQUE` | Unique values only |
| `LIST_WRITE_INSERT_BOUNDED` | Enforce boundaries |
| `LIST_WRITE_NO_FAIL` | No-fail on violation |
| `LIST_WRITE_PARTIAL` | Allow partial success |

## Map CDT

### Return Type

| Constant | Description |
|----------|-------------|
| `MAP_RETURN_NONE` | No return |
| `MAP_RETURN_INDEX` | Index |
| `MAP_RETURN_REVERSE_INDEX` | Reverse index |
| `MAP_RETURN_RANK` | Rank |
| `MAP_RETURN_REVERSE_RANK` | Reverse rank |
| `MAP_RETURN_COUNT` | Count |
| `MAP_RETURN_KEY` | Key |
| `MAP_RETURN_VALUE` | Value |
| `MAP_RETURN_KEY_VALUE` | Key-value pair |
| `MAP_RETURN_EXISTS` | Boolean |

### Order

| Constant | Description |
|----------|-------------|
| `MAP_UNORDERED` | Unordered (default) |
| `MAP_KEY_ORDERED` | Key-ordered |
| `MAP_KEY_VALUE_ORDERED` | Key-value ordered |

### Write Flags

| Constant | Description |
|----------|-------------|
| `MAP_WRITE_FLAGS_DEFAULT` | Default |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | Create only |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | Update only |
| `MAP_WRITE_FLAGS_NO_FAIL` | No-fail |
| `MAP_WRITE_FLAGS_PARTIAL` | Partial success |
| `MAP_UPDATE` | Update map |
| `MAP_UPDATE_ONLY` | Update existing only |
| `MAP_CREATE_ONLY` | Create new only |

## Bit / HLL Write Flags

| Constant | Description |
|----------|-------------|
| `BIT_WRITE_DEFAULT` | Default |
| `BIT_WRITE_CREATE_ONLY` | Create only |
| `BIT_WRITE_UPDATE_ONLY` | Update only |
| `BIT_WRITE_NO_FAIL` | No-fail |
| `BIT_WRITE_PARTIAL` | Partial |
| `HLL_WRITE_DEFAULT` | Default |
| `HLL_WRITE_CREATE_ONLY` | Create only |
| `HLL_WRITE_UPDATE_ONLY` | Update only |
| `HLL_WRITE_NO_FAIL` | No-fail |
| `HLL_WRITE_ALLOW_FOLD` | Allow fold |

## Privilege Codes

| Constant | Description |
|----------|-------------|
| `PRIV_READ` | Read |
| `PRIV_WRITE` | Write |
| `PRIV_READ_WRITE` | Read-write |
| `PRIV_READ_WRITE_UDF` | Read-write-UDF |
| `PRIV_SYS_ADMIN` | System admin |
| `PRIV_USER_ADMIN` | User admin |
| `PRIV_DATA_ADMIN` | Data admin |
| `PRIV_UDF_ADMIN` | UDF admin |
| `PRIV_SINDEX_ADMIN` | Secondary index admin |
| `PRIV_TRUNCATE` | Truncate |

## Status Codes

| Constant | Description |
|----------|-------------|
| `AEROSPIKE_OK` | Success |
| `AEROSPIKE_ERR_SERVER` | Server error |
| `AEROSPIKE_ERR_RECORD_NOT_FOUND` | Record not found |
| `AEROSPIKE_ERR_RECORD_GENERATION` | Generation mismatch |
| `AEROSPIKE_ERR_PARAM` | Invalid parameter |
| `AEROSPIKE_ERR_RECORD_EXISTS` | Record exists |
| `AEROSPIKE_ERR_BIN_EXISTS` | Bin exists |
| `AEROSPIKE_ERR_TIMEOUT` | Timeout |
| `AEROSPIKE_ERR_BIN_TYPE` | Bin type mismatch |
| `AEROSPIKE_ERR_RECORD_TOO_BIG` | Record too big |
| `AEROSPIKE_ERR_BIN_NOT_FOUND` | Bin not found |
| `AEROSPIKE_ERR_INVALID_NAMESPACE` | Invalid namespace |
| `AEROSPIKE_ERR_BIN_NAME` | Invalid bin name |
| `AEROSPIKE_ERR_FILTERED_OUT` | Filtered out |
| `AEROSPIKE_ERR_UDF` | UDF error |
| `AEROSPIKE_ERR_INDEX_FOUND` | Index exists |
| `AEROSPIKE_ERR_INDEX_NOT_FOUND` | Index not found |
| `AEROSPIKE_ERR_QUERY_ABORTED` | Query aborted |
| `AEROSPIKE_ERR_CLIENT` | Client error |
| `AEROSPIKE_ERR_CONNECTION` | Connection error |
| `AEROSPIKE_ERR_CLUSTER` | Cluster error |
| `AEROSPIKE_ERR_INVALID_HOST` | Invalid host |
| `AEROSPIKE_ERR_NO_MORE_CONNECTIONS` | No connections |

See `__init__.pyi` for the complete list.
