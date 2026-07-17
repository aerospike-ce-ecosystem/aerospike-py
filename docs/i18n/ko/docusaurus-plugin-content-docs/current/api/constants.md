---
title: 상수
sidebar_label: 상수
sidebar_position: 4
description: aerospike-py API에서 사용하는 모든 상수
---

```python
import aerospike_py as aerospike
```

## Policy

### Key

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_KEY_DIGEST` | 0 | digest 만 저장 (default) |
| `POLICY_KEY_SEND` | 1 | key 를 send 하고 저장 |

### Exists

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_EXISTS_IGNORE` | 0 | 무조건 write; create 또는 update (default) |
| `POLICY_EXISTS_UPDATE` | 1 | `POLICY_EXISTS_UPDATE_ONLY` 의 alias |
| `POLICY_EXISTS_UPDATE_ONLY` | 1 | update 만; record 없으면 실패 |
| `POLICY_EXISTS_REPLACE` | 2 | 모든 bin 교체; create 또는 update |
| `POLICY_EXISTS_REPLACE_ONLY` | 3 | replace 만; record 없으면 실패 |
| `POLICY_EXISTS_CREATE_ONLY` | 4 | create 만; record 존재 시 실패 |

### Generation

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_GEN_IGNORE` | 0 | generation 무시 (default) |
| `POLICY_GEN_EQ` | 1 | gen 일치 시에만 write |
| `POLICY_GEN_GT` | 2 | gen 이 더 클 때만 write |

### Replica

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_REPLICA_MASTER` | 0 | master 에서 read |
| `POLICY_REPLICA_SEQUENCE` | 1 | round-robin (default) |
| `POLICY_REPLICA_PREFER_RACK` | 2 | rack-local 선호 |

### Commit Level

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_COMMIT_LEVEL_ALL` | 0 | 모든 replica 대기 |
| `POLICY_COMMIT_LEVEL_MASTER` | 1 | master 만 |

### Read Mode AP

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_READ_MODE_AP_ONE` | 0 | 한 node 에서 read |
| `POLICY_READ_MODE_AP_ALL` | 1 | 모든 node 에서 read |

### Batch Concurrency

batch request 가 cluster node 들에 fan out 되는 방식 제어. [`BatchPolicy`](types.md#batchpolicy) 의 ``concurrency`` key. 다른 integer 값은 parse 시 ``ValueError``. (aerospike-core 2.0 에는 `MaxThreads(n)` variant 없음.)

| Constant | Value | 설명 |
|----------|-------|-------------|
| `BATCH_CONCURRENCY_SEQUENTIAL` | 0 | per-node 하위 request 를 한 번에 하나씩 send. peak load 낮음, latency 높음. |
| `BATCH_CONCURRENCY_PARALLEL` | 1 | Default. 모든 per-node 하위 request 를 병렬로 send. |

### Read Touch TTL Percent

``read_touch_ttl_percent`` policy key 의 특수 값 (server v8+). integer 1–100 은 percentage, 아래 상수는 특수 의미 sentinel.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `READ_TOUCH_TTL_PERCENT_SERVER_DEFAULT` | 0 | namespace 의 `default-read-touch-ttl-pct` 사용 |
| `READ_TOUCH_TTL_PERCENT_DONT_RESET` | -1 | read 시 TTL 절대 reset 안 함 |

### Query Duration

예상 query duration 에 대해 server 에게 주는 hint. `QueryPolicy` 의 ``expected_duration`` key.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `QUERY_DURATION_LONG` | 0 | Default. node 당 record 많은 장시간 query. |
| `QUERY_DURATION_SHORT` | 1 | node 당 record 적은 low-latency query (server 6.0+). |
| `QUERY_DURATION_LONG_RELAX_AP` | 2 | relaxed AP consistency 의 long query (server 7.1+). |

## TTL

| Constant | Value | 설명 |
|----------|-------|-------------|
| `TTL_NAMESPACE_DEFAULT` | 0 | namespace default 사용 |
| `TTL_NEVER_EXPIRE` | -1 | 영원히 만료 안 됨 |
| `TTL_DONT_UPDATE` | -2 | write 시 TTL update 안 함 |
| `TTL_CLIENT_DEFAULT` | -3 | client default 사용 |

## Auth Mode

| Constant | Value | 설명 |
|----------|-------|-------------|
| `AUTH_INTERNAL` | 0 | internal 인증 |
| `AUTH_EXTERNAL` | 1 | external (LDAP) |
| `AUTH_PKI` | 2 | PKI 인증 |

## Operator

`operate()` 와 `batch_operate()` 와 함께 사용.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `OPERATOR_READ` | 1 | bin read |
| `OPERATOR_WRITE` | 2 | bin write |
| `OPERATOR_INCR` | 5 | int/float bin increment |
| `OPERATOR_APPEND` | 9 | string bin 에 append |
| `OPERATOR_PREPEND` | 10 | string bin 에 prepend |
| `OPERATOR_TOUCH` | 11 | record TTL reset |
| `OPERATOR_DELETE` | 14 | record 삭제 |

## Index Type

| Constant | Value | 설명 |
|----------|-------|-------------|
| `INDEX_NUMERIC` | 0 | Numeric |
| `INDEX_STRING` | 1 | String |
| `INDEX_BLOB` | 2 | Blob |
| `INDEX_GEO2DSPHERE` | 3 | Geospatial |

## Index Collection Type

| Constant | Value | 설명 |
|----------|-------|-------------|
| `INDEX_TYPE_DEFAULT` | 0 | scalar (default) |
| `INDEX_TYPE_LIST` | 1 | list element |
| `INDEX_TYPE_MAPKEYS` | 2 | map key |
| `INDEX_TYPE_MAPVALUES` | 3 | map value |

## Log Level

| Constant | Value | 설명 |
|----------|-------|-------------|
| `LOG_LEVEL_OFF` | -1 | 비활성 |
| `LOG_LEVEL_ERROR` | 0 | Error 만 |
| `LOG_LEVEL_WARN` | 1 | Warning+ |
| `LOG_LEVEL_INFO` | 2 | Info+ |
| `LOG_LEVEL_DEBUG` | 3 | Debug+ |
| `LOG_LEVEL_TRACE` | 4 | 전체 |

## Serializer

| Constant | Value | 설명 |
|----------|-------|-------------|
| `SERIALIZER_NONE` | 0 | 직렬화 없음 |
| `SERIALIZER_PYTHON` | 1 | Python pickle |
| `SERIALIZER_USER` | 2 | 사용자 정의 |

## List CDT

### Return Type

| Constant | 설명 |
|----------|-------------|
| `LIST_RETURN_NONE` | 반환 없음 |
| `LIST_RETURN_INDEX` | index |
| `LIST_RETURN_REVERSE_INDEX` | reverse index |
| `LIST_RETURN_RANK` | rank |
| `LIST_RETURN_REVERSE_RANK` | reverse rank |
| `LIST_RETURN_COUNT` | count |
| `LIST_RETURN_VALUE` | value |
| `LIST_RETURN_EXISTS` | boolean |

### Order

| Constant | 설명 |
|----------|-------------|
| `LIST_UNORDERED` | unordered (default) |
| `LIST_ORDERED` | ordered |

### Sort Flag

| Constant | 설명 |
|----------|-------------|
| `LIST_SORT_DEFAULT` | default sort |
| `LIST_SORT_DROP_DUPLICATES` | 중복 drop |

### Write Flag

| Constant | 설명 |
|----------|-------------|
| `LIST_WRITE_DEFAULT` | Default |
| `LIST_WRITE_ADD_UNIQUE` | unique value 만 |
| `LIST_WRITE_INSERT_BOUNDED` | 경계 enforce |
| `LIST_WRITE_NO_FAIL` | 위반 시 no-fail |
| `LIST_WRITE_PARTIAL` | 부분 성공 허용 |

## Map CDT

### Return Type

| Constant | 설명 |
|----------|-------------|
| `MAP_RETURN_NONE` | 반환 없음 |
| `MAP_RETURN_INDEX` | index |
| `MAP_RETURN_REVERSE_INDEX` | reverse index |
| `MAP_RETURN_RANK` | rank |
| `MAP_RETURN_REVERSE_RANK` | reverse rank |
| `MAP_RETURN_COUNT` | count |
| `MAP_RETURN_KEY` | key |
| `MAP_RETURN_VALUE` | value |
| `MAP_RETURN_KEY_VALUE` | key-value 쌍 |
| `MAP_RETURN_EXISTS` | boolean |

### Order

| Constant | 설명 |
|----------|-------------|
| `MAP_UNORDERED` | unordered (default) |
| `MAP_KEY_ORDERED` | key-ordered |
| `MAP_KEY_VALUE_ORDERED` | key-value ordered |

### Write Flag

| Constant | 설명 |
|----------|-------------|
| `MAP_WRITE_FLAGS_DEFAULT` | Default |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | create 만 |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | update 만 |
| `MAP_WRITE_FLAGS_NO_FAIL` | no-fail |
| `MAP_WRITE_FLAGS_PARTIAL` | 부분 성공 |
| `MAP_UPDATE` | map update |
| `MAP_UPDATE_ONLY` | 기존만 update |
| `MAP_CREATE_ONLY` | 새 것만 create |

## Bit / HLL Write Flag

| Constant | 설명 |
|----------|-------------|
| `BIT_WRITE_DEFAULT` | Default |
| `BIT_WRITE_CREATE_ONLY` | create 만 |
| `BIT_WRITE_UPDATE_ONLY` | update 만 |
| `BIT_WRITE_NO_FAIL` | no-fail |
| `BIT_WRITE_PARTIAL` | partial |
| `HLL_WRITE_DEFAULT` | Default |
| `HLL_WRITE_CREATE_ONLY` | create 만 |
| `HLL_WRITE_UPDATE_ONLY` | update 만 |
| `HLL_WRITE_NO_FAIL` | no-fail |
| `HLL_WRITE_ALLOW_FOLD` | fold 허용 |

## Privilege Code

`Privilege.code` 는 int 상수 또는 canonical string 이름 둘 다 허용
(case-insensitive; `_` 는 `-` 의 동의어).

| Constant | Name | 설명 |
|----------|------|-------------|
| `PRIV_READ` | `"read"` | Read |
| `PRIV_WRITE` | `"write"` | Write |
| `PRIV_READ_WRITE` | `"read-write"` | Read-write |
| `PRIV_READ_WRITE_UDF` | `"read-write-udf"` | Read-write-UDF |
| `PRIV_SYS_ADMIN` | `"sys-admin"` | System admin |
| `PRIV_USER_ADMIN` | `"user-admin"` | User admin |
| `PRIV_DATA_ADMIN` | `"data-admin"` | Data admin |
| `PRIV_UDF_ADMIN` | `"udf-admin"` | UDF admin |
| `PRIV_SINDEX_ADMIN` | `"sindex-admin"` | Secondary index admin |
| `PRIV_TRUNCATE` | `"truncate"` | Truncate |

## Status Code

| Constant | 설명 |
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

전체 list 는 `__init__.pyi` 참조.
