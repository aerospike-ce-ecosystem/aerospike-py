---
title: Exceptions
sidebar_label: Exceptions
sidebar_position: 3
description: 예외 계층 구조 및 에러 처리 패턴
---

모든 예외는 `aerospike` 및 `aerospike.exception`에서 사용할 수 있습니다.

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordNotFound
```

## Exception Hierarchy

```
Exception
└── AerospikeError
    ├── ClientError
    ├── ClusterError
    ├── InvalidArgError
    ├── TimeoutError
    ├── ServerError
    │   ├── IndexError
    │   │   ├── IndexNotFound
    │   │   └── IndexFoundError
    │   ├── QueryError
    │   │   └── QueryAbortedError
    │   ├── AdminError
    │   └── UDFError
    └── RecordError
        ├── RecordNotFound
        ├── RecordExistsError
        ├── RecordGenerationError
        ├── RecordTooBig
        ├── BinNameError
        ├── BinExistsError
        ├── BinNotFound
        ├── BinTypeError
        └── FilteredOut
```

## Base Exceptions

| Exception | 설명 |
|-----------|-------------|
| `AerospikeError` | 모든 Aerospike 예외의 기본 클래스 |
| `ClientError` | 클라이언트 측 오류 (연결, 설정) |
| `ClusterError` | 클러스터 연결/탐색 오류 |
| `InvalidArgError` | 메서드에 잘못된 인수가 전달됨 |
| `TimeoutError` | 작업 시간 초과 |
| `ServerError` | 서버 측 오류 |
| `RecordError` | 레코드 수준 작업 오류 |

## Record Exceptions

| Exception | 설명 |
|-----------|-------------|
| `RecordNotFound` | 레코드가 존재하지 않음 |
| `RecordExistsError` | 레코드가 이미 존재함 (CREATE_ONLY 정책) |
| `RecordGenerationError` | 세대 불일치 (Optimistic Locking) |
| `RecordTooBig` | 레코드가 크기 제한을 초과함 |
| `BinNameError` | 잘못된 빈 이름 (너무 길거나 유효하지 않은 문자) |
| `BinExistsError` | 빈이 이미 존재함 |
| `BinNotFound` | 빈이 존재하지 않음 |
| `BinTypeError` | 빈 타입 불일치 |
| `FilteredOut` | Expression에 의해 레코드가 필터링됨 |

## Server Exceptions

| Exception | 설명 |
|-----------|-------------|
| `IndexError` | Secondary Index 작업 오류 |
| `IndexNotFound` | 인덱스가 존재하지 않음 |
| `IndexFoundError` | 인덱스가 이미 존재함 |
| `QueryError` | 쿼리 실행 오류 |
| `QueryAbortedError` | 쿼리가 중단됨 |
| `AdminError` | 관리 작업 오류 |
| `UDFError` | UDF 등록/실행 오류 |

## Error Handling Examples

### Basic Error Handling

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordNotFound, AerospikeError

try:
    _, meta, bins = client.get(("test", "demo", "nonexistent"))
except RecordNotFound:
    print("Record not found")
except AerospikeError as e:
    print(f"Aerospike error: {e}")
```

### Optimistic Locking

```python
from aerospike_py.exception import RecordGenerationError

try:
    _, meta, bins = client.get(key)
    client.put(key, {"val": bins["val"] + 1},
               meta={"gen": meta["gen"]},
               policy={"gen": aerospike.POLICY_GEN_EQ})
except RecordGenerationError:
    print("Record was modified by another client")
```

### Create Only

```python
from aerospike_py.exception import RecordExistsError

try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    print("Record already exists")
```

### Connection Errors

```python
from aerospike_py.exception import ClientError, ClusterError, TimeoutError

try:
    client = aerospike.client(config).connect()
except ClusterError:
    print("Cannot connect to cluster")
except TimeoutError:
    print("Connection timed out")
except ClientError as e:
    print(f"Client error: {e}")
```
