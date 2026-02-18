---
title: Types
sidebar_label: Types
sidebar_position: 2
description: aerospike-py의 NamedTuple 반환 타입과 TypedDict 입력 타입 레퍼런스
---

aerospike-py는 반환값에 **NamedTuple** 클래스를, 입력 파라미터에 **TypedDict** 클래스를 사용합니다.
모든 타입은 최상위 패키지 또는 `aerospike_py.types`에서 import할 수 있습니다.

```python
from aerospike_py import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
# 또는
from aerospike_py.types import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
```

## 반환 타입 (NamedTuple)

NamedTuple 반환 타입은 속성 접근과 튜플 언패킹을 모두 지원합니다 (하위 호환성).

### `Record`

읽기 및 operate 메서드가 반환하는 전체 레코드입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | `AerospikeKey \| None` | 레코드 키 (`POLICY_KEY_DIGEST`이면 `None`) |
| `meta` | `RecordMetadata \| None` | 레코드 메타데이터 |
| `bins` | `dict[str, Any] \| None` | 빈 이름-값 쌍 |

**반환하는 메서드**: `get()`, `select()`, `operate()`, `batch_operate()`, `batch_remove()`, `Query.results()`, `Scan.results()`

```python
record: Record = client.get(key)
print(record.meta.gen)   # 속성 접근
print(record.bins)       # {"name": "Alice", "age": 30}

key, meta, bins = record  # 튜플 언패킹 (하위 호환)
```

### `RecordMetadata`

generation과 TTL을 포함하는 레코드 메타데이터입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `gen` | `int` | 레코드 generation (낙관적 잠금 버전) |
| `ttl` | `int` | 레코드 TTL (초 단위) |

```python
record = client.get(key)
print(record.meta.gen)  # 1
print(record.meta.ttl)  # 2591998
```

### `AerospikeKey`

서버가 반환하는 레코드 키입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `namespace` | `str` | 네임스페이스 이름 |
| `set_name` | `str` | 세트 이름 |
| `user_key` | `str \| int \| bytes \| None` | 사용자 제공 기본 키 (`POLICY_KEY_DIGEST`이면 `None`) |
| `digest` | `bytes` | 20바이트 RIPEMD-160 다이제스트 |

```python
record = client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})
print(record.key.namespace)   # "test"
print(record.key.set_name)    # "demo"
print(record.key.user_key)    # "user1"
```

### `ExistsResult`

존재 여부 확인 결과입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | `AerospikeKey \| None` | 레코드 키 |
| `meta` | `RecordMetadata \| None` | 메타데이터 (레코드가 없으면 `None`) |

**반환하는 메서드**: `exists()`

```python
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")

_, meta = result  # 튜플 언패킹
```

### `InfoNodeResult`

클러스터 노드별 info 명령 결과입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `node_name` | `str` | 클러스터 노드 이름 |
| `error_code` | `int` | 성공 시 0 |
| `response` | `str` | Info 응답 문자열 |

**반환하는 메서드**: `info_all()`

```python
results: list[InfoNodeResult] = client.info_all("namespaces")
for result in results:
    print(f"{result.node_name}: {result.response}")
```

### `OperateOrderedResult`

`operate_ordered()`의 순서 보존 결과입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | `AerospikeKey \| None` | 레코드 키 |
| `meta` | `RecordMetadata \| None` | 레코드 메타데이터 |
| `ordered_bins` | `list[BinTuple]` | 순서가 보존된 연산 결과 |

**반환하는 메서드**: `operate_ordered()`

```python
result: OperateOrderedResult = client.operate_ordered(key, ops)
for bin_tuple in result.ordered_bins:
    print(f"{bin_tuple.name} = {bin_tuple.value}")
```

### `BinTuple`

순서 보존 결과에서 사용되는 단일 빈 이름-값 쌍입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | `str` | 빈 이름 |
| `value` | `Any` | 빈 값 |

## API → 반환 타입 빠른 참조

| 메서드 | 반환 타입 |
|--------|-----------|
| `get()` | `Record` |
| `select()` | `Record` |
| `exists()` | `ExistsResult` |
| `operate()` | `Record` |
| `operate_ordered()` | `OperateOrderedResult` |
| `info_all()` | `list[InfoNodeResult]` |
| `batch_read()` | `BatchRecords` |
| `batch_operate()` | `list[Record]` |
| `batch_remove()` | `list[Record]` |
| `Query.results()` | `list[Record]` |
| `Scan.results()` | `list[Record]` |
| `scan()` (async) | `list[Record]` |

---

## 입력 타입 (TypedDict)

TypedDict 입력 타입은 `policy` 및 `meta` 파라미터에 대한 IDE 자동완성과 타입 체크를 제공합니다.
모든 필드는 선택적(`total=False`)입니다.

### `ClientConfig`

클라이언트 생성을 위한 설정 딕셔너리입니다.

**사용하는 메서드**: `aerospike_py.client(config)`, `AsyncClient(config)`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `hosts` | `list[tuple[str, int]]` | *필수* | 클러스터 시드 노드 |
| `cluster_name` | `str` | | 예상 클러스터 이름 |
| `auth_mode` | `int` | `AUTH_INTERNAL` | 인증 모드 (`AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI`) |
| `user` | `str` | | 인증 사용자명 |
| `password` | `str` | | 인증 비밀번호 |
| `timeout` | `int` | `1000` | 연결 타임아웃 (ms) |
| `idle_timeout` | `int` | | 연결 유휴 타임아웃 (ms) |
| `max_conns_per_node` | `int` | | 노드당 최대 연결 수 |
| `min_conns_per_node` | `int` | | 노드당 최소 연결 수 |
| `tend_interval` | `int` | | 클러스터 tend 간격 (ms) |
| `use_services_alternate` | `bool` | `False` | 대체 서비스 주소 사용 |

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
    "timeout": 5000,
}
client = aerospike_py.client(config).connect()
```

### `ReadPolicy`

읽기 작업을 위한 정책입니다.

**사용하는 메서드**: `get()`, `select()`, `exists()`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `socket_timeout` | `int` | `30000` | 소켓 유휴 타임아웃 (ms) |
| `total_timeout` | `int` | `1000` | 전체 트랜잭션 타임아웃 (ms) |
| `max_retries` | `int` | `2` | 최대 재시도 횟수 |
| `sleep_between_retries` | `int` | `0` | 재시도 간 대기 시간 (ms) |
| `filter_expression` | `Any` | | Expression 필터 (deprecated, `expressions` 사용 권장) |
| `expressions` | `Any` | | `aerospike_py.exp`로 빌드한 Expression 필터 |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | 레플리카 알고리즘 |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP 읽기 일관성 수준 |

```python
policy: ReadPolicy = {
    "total_timeout": 5000,
    "max_retries": 3,
}
record = client.get(key, policy=policy)
```

### `WritePolicy`

쓰기 작업을 위한 정책입니다.

**사용하는 메서드**: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `socket_timeout` | `int` | `30000` | 소켓 유휴 타임아웃 (ms) |
| `total_timeout` | `int` | `1000` | 전체 트랜잭션 타임아웃 (ms) |
| `max_retries` | `int` | `0` | 최대 재시도 횟수 |
| `durable_delete` | `bool` | `False` | 영구 삭제 사용 (Enterprise 전용) |
| `key` | `int` | `POLICY_KEY_DIGEST` | 키 전송 정책 (`POLICY_KEY_DIGEST`, `POLICY_KEY_SEND`) |
| `exists` | `int` | `POLICY_EXISTS_IGNORE` | 존재 정책 (`POLICY_EXISTS_*`) |
| `gen` | `int` | `POLICY_GEN_IGNORE` | Generation 정책 (`POLICY_GEN_IGNORE`, `POLICY_GEN_EQ`, `POLICY_GEN_GT`) |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | 커밋 수준 (`POLICY_COMMIT_LEVEL_ALL`, `POLICY_COMMIT_LEVEL_MASTER`) |
| `ttl` | `int` | `0` | 레코드 TTL (초) |
| `filter_expression` | `Any` | | Expression 필터 (deprecated, `expressions` 사용 권장) |
| `expressions` | `Any` | | `aerospike_py.exp`로 빌드한 Expression 필터 |

```python
policy: WritePolicy = {
    "key": aerospike_py.POLICY_KEY_SEND,
    "exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY,
}
client.put(key, bins, policy=policy)
```

### `BatchPolicy`

배치 작업을 위한 정책입니다.

**사용하는 메서드**: `batch_read()`, `batch_operate()`, `batch_remove()`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `socket_timeout` | `int` | `30000` | 소켓 유휴 타임아웃 (ms) |
| `total_timeout` | `int` | `1000` | 전체 트랜잭션 타임아웃 (ms) |
| `max_retries` | `int` | `2` | 최대 재시도 횟수 |
| `filter_expression` | `Any` | | Expression 필터 |

```python
policy: BatchPolicy = {"total_timeout": 10000}
batch = client.batch_read(keys, policy=policy)
```

### `QueryPolicy`

쿼리 및 스캔 작업을 위한 정책입니다.

**사용하는 메서드**: `Query.results()`, `Query.foreach()`, `Scan.results()`, `Scan.foreach()`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `socket_timeout` | `int` | `30000` | 소켓 유휴 타임아웃 (ms) |
| `total_timeout` | `int` | `0` | 전체 트랜잭션 타임아웃 (0 = 제한 없음) |
| `max_retries` | `int` | `2` | 최대 재시도 횟수 |
| `max_records` | `int` | `0` | 최대 반환 레코드 수 (0 = 전부) |
| `records_per_second` | `int` | `0` | 속도 제한 (0 = 무제한) |
| `filter_expression` | `Any` | | Expression 필터 (deprecated, `expressions` 사용 권장) |
| `expressions` | `Any` | | `aerospike_py.exp`로 빌드한 Expression 필터 |

```python
policy: QueryPolicy = {"max_records": 100}
records = query.results(policy=policy)
```

### `AdminPolicy`

관리 작업을 위한 정책입니다.

**사용하는 메서드**: `admin_create_user()`, `admin_drop_user()`, `admin_change_password()`, `admin_grant_roles()`, `admin_revoke_roles()`, `admin_query_user_info()`, `admin_query_users_info()`, `admin_create_role()`, `admin_drop_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`, `admin_query_role()`, `admin_query_roles()`, `admin_set_whitelist()`, `admin_set_quotas()`

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `timeout` | `int` | `1000` | 관리 작업 타임아웃 (ms) |

```python
policy: AdminPolicy = {"timeout": 5000}
client.admin_create_user("user", "pass", ["read-write"], policy=policy)
```

### `WriteMeta`

쓰기 작업의 메타데이터입니다.

**사용하는 메서드**: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()` — `meta` 파라미터로 사용

| 필드 | 타입 | 설명 |
|------|------|------|
| `gen` | `int` | 낙관적 잠금을 위한 예상 generation (`POLICY_GEN_EQ`와 함께 사용) |
| `ttl` | `int` | 레코드 TTL (초 단위) |

```python
# TTL 설정
meta: WriteMeta = {"ttl": 300}
client.put(key, bins, meta=meta)

# 낙관적 잠금
record = client.get(key)
meta: WriteMeta = {"gen": record.meta.gen}
client.put(key, new_bins, meta=meta, policy={"gen": aerospike_py.POLICY_GEN_EQ})
```

### `Privilege`

관리자 역할 관리를 위한 권한 정의입니다.

**사용하는 메서드**: `admin_create_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`

| 필드 | 타입 | 설명 |
|------|------|------|
| `code` | `int` | 권한 코드 (`PRIV_READ`, `PRIV_WRITE`, `PRIV_READ_WRITE` 등) |
| `ns` | `str` | 네임스페이스 범위 (빈 문자열이면 글로벌) |
| `set` | `str` | 세트 범위 (빈 문자열이면 네임스페이스 전체) |

```python
privilege: Privilege = {
    "code": aerospike_py.PRIV_READ_WRITE,
    "ns": "test",
    "set": "demo",
}
client.admin_create_role("custom_role", [privilege])
```

### `UserInfo`

관리자 쿼리가 반환하는 사용자 정보입니다.

**반환하는 메서드**: `admin_query_user_info()`, `admin_query_users_info()`

| 필드 | 타입 | 설명 |
|------|------|------|
| `user` | `str` | 사용자명 |
| `roles` | `list[str]` | 할당된 역할 이름 |
| `conns_in_use` | `int` | 활성 연결 수 |

### `RoleInfo`

관리자 쿼리가 반환하는 역할 정보입니다.

**반환하는 메서드**: `admin_query_role()`, `admin_query_roles()`

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | `str` | 역할 이름 |
| `privileges` | `list[Privilege]` | 할당된 권한 |
| `allowlist` | `list[str]` | IP 허용 목록 |
| `read_quota` | `int` | 읽기 쿼터 |
| `write_quota` | `int` | 쓰기 쿼터 |
