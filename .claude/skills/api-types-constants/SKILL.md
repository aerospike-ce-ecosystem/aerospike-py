---
name: api-types-constants
description: aerospike-py complete type definitions, constants reference, policy types, and exception hierarchy
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## 반환 타입 (NamedTuple)

```python
from aerospike_py.types import Record, AerospikeKey, RecordMetadata, ExistsResult, \
    OperateOrderedResult, BinTuple, InfoNodeResult

Record(key: AerospikeKey | None, meta: RecordMetadata | None, bins: dict[str, Any] | None)
AerospikeKey(namespace: str, set_name: str, user_key: str | int | bytes | None, digest: bytes)
RecordMetadata(gen: int, ttl: int)
ExistsResult(key: AerospikeKey | None, meta: RecordMetadata | None)  # meta is None if not found
OperateOrderedResult(key: AerospikeKey | None, meta: RecordMetadata | None, ordered_bins: list[BinTuple])
BinTuple(name: str, value: Any)
InfoNodeResult(node_name: str, error_code: int, response: str)
```

## Policy 타입

```python
# ReadPolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 2,
 "expressions": expr, "replica": POLICY_REPLICA_MASTER, "read_mode_ap": POLICY_READ_MODE_AP_ONE}

# WritePolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 0,
 "durable_delete": False, "key": POLICY_KEY_DIGEST, "exists": POLICY_EXISTS_IGNORE,
 "gen": POLICY_GEN_IGNORE, "commit_level": POLICY_COMMIT_LEVEL_ALL,
 "ttl": 0, "expressions": expr}

# WriteMeta
{"gen": 1, "ttl": 300}

# BatchPolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 2, "filter_expression": expr}

# QueryPolicy
{"socket_timeout": 30000, "total_timeout": 0, "max_retries": 2,
 "max_records": 1000, "records_per_second": 0, "expressions": expr}

# AdminPolicy
{"timeout": 5000}
```

## 주요 상수

```python
# Policy Exists
POLICY_EXISTS_IGNORE = 0         # 있으면 덮어쓰기, 없으면 생성 (기본)
POLICY_EXISTS_CREATE_ONLY = 4    # 있으면 에러
POLICY_EXISTS_UPDATE = 6         # 있으면 업데이트, 없으면 생성 (IGNORE와 동일)
POLICY_EXISTS_UPDATE_ONLY = 1    # 없으면 에러
POLICY_EXISTS_REPLACE = 2        # 전체 교체 (다른 bin 삭제)
POLICY_EXISTS_REPLACE_ONLY = 5   # 전체 교체, 없으면 에러

# Policy Gen
POLICY_GEN_IGNORE = 0   # generation 무시 (기본)
POLICY_GEN_EQ = 1       # meta.gen과 서버 gen이 같을 때만 쓰기
POLICY_GEN_GT = 2       # meta.gen이 서버 gen보다 클 때만 쓰기

# Policy Key
POLICY_KEY_DIGEST = 0   # digest만 저장 (기본)
POLICY_KEY_SEND = 1     # 원본 키도 서버에 저장

# Policy Replica
POLICY_REPLICA_MASTER = 0       # master 노드에서만 읽기
POLICY_REPLICA_SEQUENCE = 1     # 순차 복제본 읽기
POLICY_REPLICA_PREFER_RACK = 2  # 같은 rack 우선

# Policy Commit Level
POLICY_COMMIT_LEVEL_ALL = 0     # 모든 복제본 커밋 (기본)
POLICY_COMMIT_LEVEL_MASTER = 1  # master만 커밋

# Policy Read Mode AP
POLICY_READ_MODE_AP_ONE = 0  # 하나의 노드에서 읽기 (기본)
POLICY_READ_MODE_AP_ALL = 1  # 모든 노드에서 읽기

# TTL
TTL_NAMESPACE_DEFAULT = 0   # namespace 기본값 사용
TTL_NEVER_EXPIRE = -1       # 만료 없음
TTL_DONT_UPDATE = -2        # TTL 변경하지 않음
TTL_CLIENT_DEFAULT = -3     # 클라이언트 정책 기본값

# Operator (operate용)
OPERATOR_READ = 1       # bin 읽기
OPERATOR_WRITE = 2      # bin 쓰기
OPERATOR_INCR = 5       # 숫자 증가
OPERATOR_APPEND = 9     # 문자열 뒤에 추가
OPERATOR_PREPEND = 10   # 문자열 앞에 추가
OPERATOR_TOUCH = 11     # TTL 리셋
OPERATOR_DELETE = 12    # 레코드 삭제

# Map/List Return Type
MAP_RETURN_NONE = 0           # 반환 없음
MAP_RETURN_INDEX = 1          # 인덱스 반환
MAP_RETURN_REVERSE_INDEX = 2  # 역순 인덱스
MAP_RETURN_RANK = 3           # 랭크 반환
MAP_RETURN_REVERSE_RANK = 4   # 역순 랭크
MAP_RETURN_COUNT = 5          # 개수 반환
MAP_RETURN_KEY = 6            # 키 반환
MAP_RETURN_VALUE = 7          # 값 반환
MAP_RETURN_KEY_VALUE = 8      # 키-값 쌍 반환
MAP_RETURN_EXISTS = 9         # 존재 여부

LIST_RETURN_NONE = 0          # 반환 없음
LIST_RETURN_VALUE = 7         # 값 반환
LIST_RETURN_COUNT = 5         # 개수 반환
LIST_RETURN_INDEX = 1         # 인덱스 반환
LIST_RETURN_RANK = 3          # 랭크 반환

# Index Type
INDEX_NUMERIC, INDEX_STRING, INDEX_BLOB, INDEX_GEO2DSPHERE
INDEX_TYPE_DEFAULT, INDEX_TYPE_LIST, INDEX_TYPE_MAPKEYS, INDEX_TYPE_MAPVALUES

# Privilege
PRIV_READ, PRIV_WRITE, PRIV_READ_WRITE, PRIV_READ_WRITE_UDF
PRIV_SYS_ADMIN, PRIV_USER_ADMIN, PRIV_DATA_ADMIN
PRIV_UDF_ADMIN, PRIV_SINDEX_ADMIN, PRIV_TRUNCATE

# Auth
AUTH_INTERNAL = 0, AUTH_EXTERNAL = 1, AUTH_PKI = 2

# Serializer
SERIALIZER_NONE, SERIALIZER_PYTHON, SERIALIZER_USER

# Map Order / Write Flags
MAP_UNORDERED, MAP_KEY_ORDERED, MAP_KEY_VALUE_ORDERED
MAP_WRITE_FLAGS_DEFAULT, MAP_WRITE_FLAGS_CREATE_ONLY, MAP_WRITE_FLAGS_UPDATE_ONLY
MAP_WRITE_FLAGS_NO_FAIL, MAP_WRITE_FLAGS_PARTIAL

# List Order / Sort / Write Flags
LIST_UNORDERED, LIST_ORDERED
LIST_SORT_DEFAULT, LIST_SORT_DROP_DUPLICATES
LIST_WRITE_DEFAULT, LIST_WRITE_ADD_UNIQUE, LIST_WRITE_INSERT_BOUNDED
LIST_WRITE_NO_FAIL, LIST_WRITE_PARTIAL

# Bit / HLL Write Flags
BIT_WRITE_DEFAULT, BIT_WRITE_CREATE_ONLY, BIT_WRITE_UPDATE_ONLY
HLL_WRITE_DEFAULT, HLL_WRITE_CREATE_ONLY, HLL_WRITE_UPDATE_ONLY, HLL_WRITE_ALLOW_FOLD
```

## 예외

```python
try:
    record = client.get(key)
except aerospike_py.RecordNotFound:
    print("Not found")
except aerospike_py.AerospikeTimeoutError:
    print("Timeout")
except aerospike_py.AerospikeError as e:
    print(f"Error: {e}")

# 예외 계층:
# AerospikeError (기본)
# +-- ClientError (클라이언트 에러, 연결 안됨 등)
# +-- ClusterError (클러스터 연결 실패)
# +-- InvalidArgError (잘못된 인자)
# +-- AerospikeTimeoutError (타임아웃)
# +-- TimeoutError (deprecated alias)
# +-- RecordError (레코드 관련)
# |   +-- RecordNotFound
# |   +-- RecordExistsError
# |   +-- RecordGenerationError
# |   +-- RecordTooBig
# |   +-- BinNameError
# |   +-- BinExistsError
# |   +-- BinNotFound
# |   +-- BinTypeError
# |   +-- FilteredOut
# +-- ServerError (서버 관련)
#     +-- AerospikeIndexError (IndexError는 deprecated alias)
#     |   +-- IndexNotFound
#     |   +-- IndexFoundError
#     +-- QueryError
#     |   +-- QueryAbortedError
#     +-- AdminError
#     +-- UDFError
```
