---
title: Constants
sidebar_label: Constants
sidebar_position: 4
description: Policy, TTL, operator, index type, and other constants used across the aerospike-py API.
---

All constants are available directly from the `aerospike` module.

```python
import aerospike_py as aerospike
print(aerospike.POLICY_KEY_SEND)
```

## Policy Key

Controls whether the key is stored on the server.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_KEY_DIGEST` | 0 | Store only the digest (default) |
| `POLICY_KEY_SEND` | 1 | Send and store the key |

## Policy Exists

Controls behavior when a record already exists.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_EXISTS_IGNORE` | 0 | Write regardless (default) |
| `POLICY_EXISTS_UPDATE` | 1 | Update existing record |
| `POLICY_EXISTS_UPDATE_ONLY` | 2 | Fail if record does not exist |
| `POLICY_EXISTS_REPLACE` | 3 | Replace all bins |
| `POLICY_EXISTS_REPLACE_ONLY` | 4 | Replace only if exists |
| `POLICY_EXISTS_CREATE_ONLY` | 5 | Fail if record already exists |

## Policy Generation

Controls generation-based conflict resolution.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_GEN_IGNORE` | 0 | Ignore generation (default) |
| `POLICY_GEN_EQ` | 1 | Write only if gen matches |
| `POLICY_GEN_GT` | 2 | Write only if gen is greater |

## Policy Replica

Controls which replica to read from.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_REPLICA_MASTER` | 0 | Read from master |
| `POLICY_REPLICA_SEQUENCE` | 1 | Round-robin across replicas |
| `POLICY_REPLICA_PREFER_RACK` | 2 | Prefer rack-local replica |

## Policy Commit Level

Controls write commit guarantee.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_COMMIT_LEVEL_ALL` | 0 | Wait for all replicas |
| `POLICY_COMMIT_LEVEL_MASTER` | 1 | Wait for master only |

## Policy Read Mode AP

Controls read consistency in AP mode.

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_READ_MODE_AP_ONE` | 0 | Read from one node |
| `POLICY_READ_MODE_AP_ALL` | 1 | Read from all nodes |

## TTL Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TTL_NAMESPACE_DEFAULT` | 0 | Use namespace default TTL |
| `TTL_NEVER_EXPIRE` | -1 | Never expire |
| `TTL_DONT_UPDATE` | -2 | Don't update TTL on write |
| `TTL_CLIENT_DEFAULT` | -3 | Use client default TTL |

## Auth Mode

| Constant | Value | Description |
|----------|-------|-------------|
| `AUTH_INTERNAL` | 0 | Internal authentication |
| `AUTH_EXTERNAL` | 1 | External (LDAP) authentication |
| `AUTH_PKI` | 2 | PKI authentication |

## Operators

Used with `operate()` and `batch_operate()`.

| Constant | Value | Description |
|----------|-------|-------------|
| `OPERATOR_READ` | 1 | Read a bin |
| `OPERATOR_WRITE` | 2 | Write a bin |
| `OPERATOR_INCR` | 5 | Increment integer/float bin |
| `OPERATOR_APPEND` | 9 | Append to string bin |
| `OPERATOR_PREPEND` | 10 | Prepend to string bin |
| `OPERATOR_TOUCH` | 11 | Reset record TTL |
| `OPERATOR_DELETE` | 14 | Delete the record |

## Index Type

Secondary index data types.

| Constant | Value | Description |
|----------|-------|-------------|
| `INDEX_NUMERIC` | 0 | Numeric index |
| `INDEX_STRING` | 1 | String index |
| `INDEX_BLOB` | 2 | Blob index |
| `INDEX_GEO2DSPHERE` | 3 | Geospatial index |

## Index Collection Type

| Constant | Value | Description |
|----------|-------|-------------|
| `INDEX_TYPE_DEFAULT` | 0 | Default (scalar) |
| `INDEX_TYPE_LIST` | 1 | Index list elements |
| `INDEX_TYPE_MAPKEYS` | 2 | Index map keys |
| `INDEX_TYPE_MAPVALUES` | 3 | Index map values |

## Log Level

| Constant | Value | Description |
|----------|-------|-------------|
| `LOG_LEVEL_OFF` | -1 | Logging disabled |
| `LOG_LEVEL_ERROR` | 0 | Error only |
| `LOG_LEVEL_WARN` | 1 | Warnings and above |
| `LOG_LEVEL_INFO` | 2 | Info and above |
| `LOG_LEVEL_DEBUG` | 3 | Debug and above |
| `LOG_LEVEL_TRACE` | 4 | All messages |

## Serializer

| Constant | Value | Description |
|----------|-------|-------------|
| `SERIALIZER_NONE` | 0 | No serialization |
| `SERIALIZER_PYTHON` | 1 | Python pickle |
| `SERIALIZER_USER` | 2 | User-defined serializer |

## List Return Type

| Constant | Description |
|----------|-------------|
| `LIST_RETURN_NONE` | No return |
| `LIST_RETURN_INDEX` | Return index |
| `LIST_RETURN_REVERSE_INDEX` | Return reverse index |
| `LIST_RETURN_RANK` | Return rank |
| `LIST_RETURN_REVERSE_RANK` | Return reverse rank |
| `LIST_RETURN_COUNT` | Return count |
| `LIST_RETURN_VALUE` | Return value |
| `LIST_RETURN_EXISTS` | Return existence boolean |

## List Order

| Constant | Description |
|----------|-------------|
| `LIST_UNORDERED` | Unordered list |
| `LIST_ORDERED` | Ordered list |

## List Sort Flags

| Constant | Description |
|----------|-------------|
| `LIST_SORT_DEFAULT` | Default sort |
| `LIST_SORT_DROP_DUPLICATES` | Drop duplicates during sort |

## List Write Flags

| Constant | Description |
|----------|-------------|
| `LIST_WRITE_DEFAULT` | Default write |
| `LIST_WRITE_ADD_UNIQUE` | Only add unique values |
| `LIST_WRITE_INSERT_BOUNDED` | Enforce list boundaries |
| `LIST_WRITE_NO_FAIL` | Don't fail on policy violation |
| `LIST_WRITE_PARTIAL` | Allow partial success |

## Map Return Type

| Constant | Description |
|----------|-------------|
| `MAP_RETURN_NONE` | No return |
| `MAP_RETURN_INDEX` | Return index |
| `MAP_RETURN_REVERSE_INDEX` | Return reverse index |
| `MAP_RETURN_RANK` | Return rank |
| `MAP_RETURN_REVERSE_RANK` | Return reverse rank |
| `MAP_RETURN_COUNT` | Return count |
| `MAP_RETURN_KEY` | Return key |
| `MAP_RETURN_VALUE` | Return value |
| `MAP_RETURN_KEY_VALUE` | Return key-value pair |
| `MAP_RETURN_EXISTS` | Return existence boolean |

## Map Order

| Constant | Description |
|----------|-------------|
| `MAP_UNORDERED` | Unordered map |
| `MAP_KEY_ORDERED` | Key-ordered map |
| `MAP_KEY_VALUE_ORDERED` | Key-value ordered map |

## Map Write Flags

| Constant | Description |
|----------|-------------|
| `MAP_WRITE_FLAGS_DEFAULT` | Default write |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | Create only |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | Update only |
| `MAP_WRITE_FLAGS_NO_FAIL` | Don't fail on policy violation |
| `MAP_WRITE_FLAGS_PARTIAL` | Allow partial success |
| `MAP_UPDATE` | Update map |
| `MAP_UPDATE_ONLY` | Update only existing keys |
| `MAP_CREATE_ONLY` | Create only new keys |

## Bit Write Flags

| Constant | Description |
|----------|-------------|
| `BIT_WRITE_DEFAULT` | Default write |
| `BIT_WRITE_CREATE_ONLY` | Create only |
| `BIT_WRITE_UPDATE_ONLY` | Update only |
| `BIT_WRITE_NO_FAIL` | Don't fail on policy violation |
| `BIT_WRITE_PARTIAL` | Allow partial success |

## HLL Write Flags

| Constant | Description |
|----------|-------------|
| `HLL_WRITE_DEFAULT` | Default write |
| `HLL_WRITE_CREATE_ONLY` | Create only |
| `HLL_WRITE_UPDATE_ONLY` | Update only |
| `HLL_WRITE_NO_FAIL` | Don't fail on policy violation |
| `HLL_WRITE_ALLOW_FOLD` | Allow fold |

## Privilege Codes

| Constant | Description |
|----------|-------------|
| `PRIV_READ` | Read privilege |
| `PRIV_WRITE` | Write privilege |
| `PRIV_READ_WRITE` | Read-write privilege |
| `PRIV_READ_WRITE_UDF` | Read-write-UDF privilege |
| `PRIV_SYS_ADMIN` | System admin |
| `PRIV_USER_ADMIN` | User admin |
| `PRIV_DATA_ADMIN` | Data admin |
| `PRIV_UDF_ADMIN` | UDF admin |
| `PRIV_SINDEX_ADMIN` | Secondary index admin |
| `PRIV_TRUNCATE` | Truncate privilege |

## Status Codes

Status codes for error identification.

| Constant | Description |
|----------|-------------|
| `AEROSPIKE_OK` | Operation successful |
| `AEROSPIKE_ERR_SERVER` | Generic server error |
| `AEROSPIKE_ERR_RECORD_NOT_FOUND` | Record not found |
| `AEROSPIKE_ERR_RECORD_GENERATION` | Generation mismatch |
| `AEROSPIKE_ERR_PARAM` | Invalid parameter |
| `AEROSPIKE_ERR_RECORD_EXISTS` | Record already exists |
| `AEROSPIKE_ERR_BIN_EXISTS` | Bin already exists |
| `AEROSPIKE_ERR_CLUSTER_KEY_MISMATCH` | Cluster key mismatch |
| `AEROSPIKE_ERR_SERVER_MEM` | Server out of memory |
| `AEROSPIKE_ERR_TIMEOUT` | Operation timed out |
| `AEROSPIKE_ERR_ALWAYS_FORBIDDEN` | Always forbidden |
| `AEROSPIKE_ERR_PARTITION_UNAVAILABLE` | Partition unavailable |
| `AEROSPIKE_ERR_BIN_TYPE` | Bin type mismatch |
| `AEROSPIKE_ERR_RECORD_TOO_BIG` | Record too big |
| `AEROSPIKE_ERR_KEY_BUSY` | Key busy |
| `AEROSPIKE_ERR_SCAN_ABORT` | Scan aborted |
| `AEROSPIKE_ERR_UNSUPPORTED_FEATURE` | Unsupported feature |
| `AEROSPIKE_ERR_BIN_NOT_FOUND` | Bin not found |
| `AEROSPIKE_ERR_DEVICE_OVERLOAD` | Device overload |
| `AEROSPIKE_ERR_KEY_MISMATCH` | Key mismatch |
| `AEROSPIKE_ERR_INVALID_NAMESPACE` | Invalid namespace |
| `AEROSPIKE_ERR_BIN_NAME` | Invalid bin name |
| `AEROSPIKE_ERR_FAIL_FORBIDDEN` | Operation forbidden |
| `AEROSPIKE_ERR_ELEMENT_NOT_FOUND` | Element not found |
| `AEROSPIKE_ERR_ELEMENT_EXISTS` | Element exists |
| `AEROSPIKE_ERR_ENTERPRISE_ONLY` | Enterprise feature only |
| `AEROSPIKE_ERR_OP_NOT_APPLICABLE` | Operation not applicable |
| `AEROSPIKE_ERR_FILTERED_OUT` | Record filtered out |
| `AEROSPIKE_ERR_LOST_CONFLICT` | Lost conflict |
| `AEROSPIKE_QUERY_END` | Query ended |
| `AEROSPIKE_SECURITY_NOT_SUPPORTED` | Security not supported |
| `AEROSPIKE_SECURITY_NOT_ENABLED` | Security not enabled |
| `AEROSPIKE_ERR_INVALID_USER` | Invalid user |
| `AEROSPIKE_ERR_NOT_AUTHENTICATED` | Not authenticated |
| `AEROSPIKE_ERR_ROLE_VIOLATION` | Role violation |
| `AEROSPIKE_ERR_UDF` | UDF error |
| `AEROSPIKE_ERR_BATCH_DISABLED` | Batch disabled |
| `AEROSPIKE_ERR_INDEX_FOUND` | Index already exists |
| `AEROSPIKE_ERR_INDEX_NOT_FOUND` | Index not found |
| `AEROSPIKE_ERR_QUERY_ABORTED` | Query aborted |
| `AEROSPIKE_ERR_CLIENT` | Client error |
| `AEROSPIKE_ERR_CONNECTION` | Connection error |
| `AEROSPIKE_ERR_CLUSTER` | Cluster error |
| `AEROSPIKE_ERR_INVALID_HOST` | Invalid host |
| `AEROSPIKE_ERR_NO_MORE_CONNECTIONS` | No more connections |
