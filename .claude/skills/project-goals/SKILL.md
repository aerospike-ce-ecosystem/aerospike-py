# Project Goals

## 핵심 목표

Aerospike Rust Client(`aerospike-rust` crate)를 PyO3로 래핑하여, Python에서 Aerospike를 고성능으로 사용할 수 있는 클라이언트 라이브러리를 만든다.

## 주요 기능 축

### 1. Sync / Async Client

- Rust 네이티브 클라이언트를 기반으로 **동기(`Client`) + 비동기(`AsyncClient`)** 양쪽 API를 제공한다.
- 공식 C 클라이언트(`aerospike` PyPI 패키지)와 **API 호환성**을 유지하면 좋지만 Rust 네이티브 클라이언트 API 스펙을 더 우선한다
- Python 3.10~3.14 (3.14t free-threaded 포함) 지원.

### 2. NumPy 통합

- `batch_read` 등 배치 연산에서 **NumPy structured array**를 입출력으로 지원한다.
- 대량 레코드를 Python dict 변환 없이 zero-copy에 가깝게 처리하여 성능을 높인다.
- optional dependency (`pip install aerospike-py[numpy]`)로 제공.

### 3. Observability (OpenTelemetry)

- **Tracing**: 각 DB 연산을 OTel span으로 자동 계측. W3C TraceContext 전파 지원.
- **Metrics**: Prometheus 형식의 연산별 지연시간 히스토그램. 내장 metrics 서버 제공.
- **Logging**: Rust 내부 로그를 Python 로그 레벨과 연동.
- optional dependency (`pip install aerospike-py[otel]`)로 제공.

## 설계 원칙

- **Rust 우선**: 핵심 로직은 Rust에서 구현하고, Python 레이어는 얇은 래퍼로 유지한다.
- **공식 클라이언트 호환**: 메서드 시그니처, 상수, 예외를 공식 C 클라이언트와 가능한 동일하게 맞춘다.
- **Type-safe**: `.pyi` 스텁을 제공하여 IDE 자동완성과 타입 체커를 완벽히 지원한다.
- **Zero Python dependency**: 기본 설치 시 외부 Python 의존성 없음. NumPy, OTel은 optional.

## 기술 스택

| 레이어        | 기술                                                 |
| ------------- | ---------------------------------------------------- |
| Core          | `aerospike` crate (2.0.0-alpha) + `aerospike-core`   |
| Binding       | PyO3 0.28 + maturin                                  |
| Async Runtime | Tokio (multi-thread) + pyo3-async-runtimes            |
| Metrics       | prometheus-client (Rust)                              |
| Tracing       | opentelemetry + opentelemetry-otlp (gRPC/Tonic)       |
| NumPy         | 직접 buffer 조작 (numpy C API via PyO3)                |

## 현재 구현 상태

### 완료

- Sync/Async Client: CRUD, batch, operate, query, index, truncate, UDF, admin
- NumPy batch_read (structured array 반환)
- Prometheus metrics (히스토그램, 내장 서버)
- OTel tracing (span 생성, TraceContext 전파)
- Logging (Rust → Python 레벨 연동)
- Expression 필터
- List/Map CDT 연산 헬퍼
- 공식 C 클라이언트 호환성 테스트 (완벽하게 호환할 필요 없음)

### 미구현 / 향후 과제

- Batch write (batch_operate로 대체 가능하나 별도 API 검토)
- batch write numpy (numpy structued array로 주어진 데이터를 records list로 batch_write하는 API 스펙)
- HyperLogLog / Bitwise 연산 헬퍼
- Connection pool 세부 설정
- Rack-aware 읽기 최적화
