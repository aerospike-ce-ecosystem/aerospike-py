---
name: api-client-crud
description: aerospike-py client creation, connection, CRUD operations (put, get, select, exists, remove, touch, append, prepend, increment), and basic policies
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## Client 생성

```python
import aerospike_py

# Sync - 메서드 체이닝
client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()

# Sync - context manager
with aerospike_py.client(config).connect() as client:
    record = client.get(("test", "demo", "key1"))

# Sync - 인증
client = aerospike_py.client(config).connect("admin", "admin")

# Async
client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 18710)]})
await client.connect()

# Async - context manager
async with aerospike_py.AsyncClient(config) as client:
    await client.connect()
    record = await client.get(("test", "demo", "key1"))
```

### ClientConfig

```python
config: dict = {
    "hosts": [("127.0.0.1", 18710)],  # 필수
    "cluster_name": "docker",           # 클러스터 이름 검증
    "auth_mode": aerospike_py.AUTH_INTERNAL,  # 인증 모드
    "user": "admin",                    # 사용자
    "password": "admin",               # 비밀번호
    "timeout": 30000,                   # 연결 타임아웃 (ms)
    "idle_timeout": 55000,             # 유휴 연결 타임아웃 (ms)
    "max_conns_per_node": 300,         # 노드당 최대 연결 수
    "min_conns_per_node": 0,           # 노드당 최소 연결 수
    "tend_interval": 1000,             # 클러스터 상태 확인 주기 (ms)
    "use_services_alternate": False,   # alternate 서비스 주소 사용
}
```

## 반환 타입 (NamedTuple)

```python
from aerospike_py.types import Record, AerospikeKey, RecordMetadata, ExistsResult

Record(key: AerospikeKey | None, meta: RecordMetadata | None, bins: dict[str, Any] | None)
AerospikeKey(namespace: str, set_name: str, user_key: str | int | bytes | None, digest: bytes)
RecordMetadata(gen: int, ttl: int)
ExistsResult(key: AerospikeKey | None, meta: RecordMetadata | None)  # meta is None if not found
```

## Connection

```python
client.connect(username=None, password=None) -> Client   # 메서드 체이닝
client.is_connected() -> bool
client.close() -> None
client.get_node_names() -> list[str]

# Async 동일 (await 필요, is_connected 제외)
await client.connect()
await client.close()
await client.get_node_names()
```

## CRUD

```python
key: tuple[str, str, str | int | bytes] = ("test", "demo", "user1")

# Write
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"score": 100}, meta={"ttl": 300})  # TTL 설정
client.put(key, {"x": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
client.put(key, {"x": 1}, meta={"gen": 2}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

# Read -> Record
record: Record = client.get(key)
record.bins     # {"name": "Alice", "age": 30}
record.meta.gen # generation number
record.meta.ttl # TTL in seconds

# Select -> Record (특정 bin만 읽기)
record: Record = client.select(key, ["name"])  # record.bins = {"name": "Alice"}

# Exists -> ExistsResult
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"Found, gen={result.meta.gen}")

# Delete
client.remove(key)
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

# Touch (TTL 리셋)
client.touch(key, val=300)

# String 연산
client.append(key, "name", "_suffix")
client.prepend(key, "name", "prefix_")

# Numeric 연산
client.increment(key, "counter", 1)      # int 증가
client.increment(key, "score", 0.5)      # float 증가
client.increment(key, "counter", -1)     # 감소

# Bin 삭제
client.remove_bin(key, ["temp_bin", "debug_bin"])

# Async: 모든 메서드에 await 추가
record = await client.get(key)
await client.put(key, {"name": "Alice"})
```

## 예외 처리

```python
try:
    record = client.get(key)
except aerospike_py.RecordNotFound:
    print("Not found")
except aerospike_py.AerospikeTimeoutError:
    print("Timeout")
except aerospike_py.AerospikeError as e:
    print(f"Error: {e}")
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

# 주요 상수
POLICY_EXISTS_IGNORE = 0         # 있으면 덮어쓰기, 없으면 생성 (기본)
POLICY_EXISTS_CREATE_ONLY = 4    # 있으면 에러
POLICY_EXISTS_UPDATE_ONLY = 1    # 없으면 에러
POLICY_EXISTS_REPLACE = 2        # 전체 교체 (다른 bin 삭제)
POLICY_GEN_IGNORE = 0            # generation 무시 (기본)
POLICY_GEN_EQ = 1                # meta.gen과 서버 gen이 같을 때만 쓰기
POLICY_KEY_DIGEST = 0            # digest만 저장 (기본)
POLICY_KEY_SEND = 1              # 원본 키도 서버에 저장
TTL_NAMESPACE_DEFAULT = 0        # namespace 기본값 사용
TTL_NEVER_EXPIRE = -1            # 만료 없음
TTL_DONT_UPDATE = -2             # TTL 변경하지 않음
```
