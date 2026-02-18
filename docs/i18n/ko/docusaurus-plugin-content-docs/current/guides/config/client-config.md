---
title: 클라이언트 설정
sidebar_label: 연결 & 설정
sidebar_position: 1
slug: /guides/client-config
description: aerospike-py 클라이언트 연결, 타임아웃, 커넥션 풀 설정 가이드
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## ClientConfig 개요

[`ClientConfig`](../../api/types.md#clientconfig) TypedDict는 `aerospike.client()` 또는 `AsyncClient()`에 전달하는 모든 연결 옵션을 정의합니다.

```python
import aerospike_py as aerospike

config = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}
client = aerospike.client(config).connect()
```

## 전체 설정 필드

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `hosts` | `list[tuple[str, int]]` | *필수* | 시드 노드 주소 `(host, port)` |
| `cluster_name` | `str` | `""` | 검증용 클러스터 이름 |
| `auth_mode` | `int` | `AUTH_INTERNAL` | 인증 모드 (`AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI`) |
| `user` | `str` | `""` | 인증 사용자명 |
| `password` | `str` | `""` | 인증 비밀번호 |
| `timeout` | `int` | `1000` | 연결 타임아웃 (ms) |
| `idle_timeout` | `int` | `55` | 풀링된 연결의 최대 유휴 시간 (초) |
| `max_conns_per_node` | `int` | `100` | 노드당 최대 연결 수 |
| `min_conns_per_node` | `int` | `0` | 노드당 사전 워밍 연결 수 |
| `tend_interval` | `int` | `1000` | 클러스터 tend 간격 (ms) |
| `use_services_alternate` | `bool` | `false` | 서비스 응답의 대체 주소 사용 |

## 호스트 설정

### 단일 노드

```python
config = {"hosts": [("127.0.0.1", 3000)]}
```

### 멀티 노드 클러스터

자동 클러스터 디스커버리를 위해 여러 시드 노드를 제공합니다:

```python
config = {
    "hosts": [
        ("node1.example.com", 3000),
        ("node2.example.com", 3000),
        ("node3.example.com", 3000),
    ],
}
```

클라이언트는 접근 가능한 시드 노드에서 모든 클러스터 노드를 자동으로 검색합니다.

### 클러스터 이름 검증

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "production",  # 클러스터 이름이 일치하지 않으면 실패
}
```

## 커넥션 풀

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "max_conns_per_node": 300,   # 기본값: 100
    "min_conns_per_node": 10,    # 사전 워밍 연결
    "idle_timeout": 55,          # 초 단위
}
```

**가이드라인:**
- `max_conns_per_node`를 노드당 예상 동시 요청 수에 맞게 설정
- `min_conns_per_node`로 콜드 스타트 지연 방지
- `idle_timeout`을 서버의 `proto-fd-idle-ms`(기본값 60초)보다 약간 낮게 설정

## 타임아웃

### 클라이언트 레벨 타임아웃

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "timeout": 30000,  # 연결 + tend 타임아웃 (ms)
}
```

### 작업별 타임아웃

[`ReadPolicy`](../../api/types.md#readpolicy) 또는 [`WritePolicy`](../../api/types.md#writepolicy)로 작업별 타임아웃을 설정합니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# 작업별 타임아웃 설정
policy = {
    "socket_timeout": 5000,   # 소켓 타임아웃 (ms)
    "total_timeout": 10000,   # 전체 작업 타임아웃 (ms)
    "max_retries": 2,         # 재시도 횟수
}
client.get(key, policy=policy)
client.put(key, bins, policy=policy)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
policy = {
    "socket_timeout": 5000,
    "total_timeout": 10000,
    "max_retries": 2,
}
await client.get(key, policy=policy)
await client.put(key, bins, policy=policy)
```

  </TabItem>
</Tabs>

**가이드라인:**
- `socket_timeout`으로 응답 없는 연결 감지; 1-5초로 설정
- `total_timeout`으로 재시도 포함 전체 시간 제한; SLA에 맞게 설정
- `max_retries`는 복원력을 높이지만 실패 시 지연 시간이 배수로 증가

## 인증

### 내부 인증

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_INTERNAL,
}
client = aerospike.client(config).connect(username="admin", password="admin")
```

### 외부 인증 (LDAP)

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "auth_mode": aerospike.AUTH_EXTERNAL,
}
client = aerospike.client(config).connect(username="ldap_user", password="ldap_pass")
```

## 클러스터 Info 명령

`info_all()`과 `info_random_node()`로 클러스터 상태를 조회합니다:

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import InfoNodeResult

# 모든 노드에 쿼리
results: list[InfoNodeResult] = client.info_all("status")
for r in results:
    print(f"{r.node_name}: {r.response}")

# 랜덤 노드에 쿼리
response: str = client.info_random_node("build")
print(f"서버 버전: {response}")

# 일반적인 info 명령어
client.info_all("namespaces")          # 네임스페이스 목록
client.info_all("sets/test")           # 'test' 네임스페이스의 set 목록
client.info_all("statistics")          # 서버 통계
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import InfoNodeResult

results: list[InfoNodeResult] = await client.info_all("status")
for r in results:
    print(f"{r.node_name}: {r.response}")

response: str = await client.info_random_node("build")
```

  </TabItem>
</Tabs>

## 로깅

```python
import aerospike_py as aerospike

# 로그 수준 설정
aerospike.set_log_level(aerospike.LOG_LEVEL_DEBUG)
```

| 상수 | 값 | 설명 |
|------|-----|------|
| `LOG_LEVEL_OFF` | -1 | 로그 비활성화 |
| `LOG_LEVEL_ERROR` | 0 | 에러만 |
| `LOG_LEVEL_WARN` | 1 | 경고 이상 |
| `LOG_LEVEL_INFO` | 2 | 정보 이상 |
| `LOG_LEVEL_DEBUG` | 3 | 디버그 이상 |
| `LOG_LEVEL_TRACE` | 4 | 전체 트레이스 |

## 모니터링

### Prometheus 메트릭

```python
# /metrics 엔드포인트 HTTP 서버 시작
aerospike.start_metrics_server(port=9464)

# Prometheus 텍스트 포맷으로 메트릭 가져오기
metrics_text = aerospike.get_metrics()

# 메트릭 서버 중지
aerospike.stop_metrics_server()
```

### OpenTelemetry 트레이싱

```python
# OTel 트레이서 초기화 (OTEL_* 환경변수로 설정)
aerospike.init_tracing()

# ... 작업 수행 ...

# 스팬 플러시 및 종료
aerospike.shutdown_tracing()
```

Span 속성: `db.system.name`, `db.namespace`, `db.collection.name`, `db.operation.name`, `server.address`, `server.port`, `db.aerospike.cluster_name`

## Sync vs Async Client

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

# Context Manager (권장)
with aerospike.client(config).connect() as client:
    client.put(key, bins)
    record = client.get(key)
# client.close()가 자동으로 호출됩니다

# 수동 라이프사이클
client = aerospike.client(config).connect()
try:
    client.put(key, bins)
finally:
    client.close()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py as aerospike

# Context Manager
async with aerospike.AsyncClient(config) as client:
    await client.connect()
    await client.put(key, bins)
    record = await client.get(key)

# 수동 라이프사이클
client = aerospike.AsyncClient(config)
await client.connect()
try:
    await client.put(key, bins)
finally:
    await client.close()
```

  </TabItem>
</Tabs>

**Async를 사용해야 하는 경우:**

- 고동시성 웹 서버 (FastAPI, aiohttp)
- 팬아웃 읽기 패턴 (여러 키를 병렬로)
- 혼합 I/O 워크로드 (데이터베이스 + HTTP + 캐시)

**Sync로 충분한 경우:**

- 간단한 스크립트 및 배치 작업
- 순차 처리 파이프라인
- 저동시성 애플리케이션
