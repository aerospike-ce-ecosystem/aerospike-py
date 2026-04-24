# `pyo3_disable_reference_pool` 테스트 결과

> 2026-04-16 | K8s 클러스터, benchmark namespace

## 테스트 목적

PyO3의 global reference pool 동기화 비용을 제거하여 Python↔Rust 경계 성능 개선 여부 확인.

## 빌드 옵션

```bash
RUSTFLAGS='--cfg pyo3_disable_reference_pool --cfg pyo3_leak_on_drop_without_reference_pool'
```

- `pyo3_disable_reference_pool`: reference pool 비활성화
- `pyo3_leak_on_drop_without_reference_pool`: GIL 없이 `Py<T>` drop 시 panic 대신 leak (안전 방어)

## 안전성 분석

async move 블록에 캡처된 `Py<T>` 객체가 future cancel 시 GIL 없이 drop될 위험:

| 위치 | 객체 | 위험도 |
|------|------|--------|
| `async_client.rs:729` | `dtype_py: Option<Py<PyAny>>` | 높음 (numpy 경로) |
| `async_client.rs:320` 등 | `key_py: Py<PyAny>` | 중간 (get/select/exists) |
| `async_client.rs:46` | `config: Py<PyAny>` | 낮음 (구조체) |

**batch_read Handle 경로 (벤치마크에서 사용)는 `Py<T>` 캡처 없음 → 안전.**

## k6 테스트 결과 (10 VUs, 60초, Istio)

### aerospike-py single mode

| Metric | baseline (pool 활성) | pool 비활성화 | 변화 |
|--------|---------------------|--------------|------|
| **avg** | **60.8ms** | **139.6ms** | **+130% 악화** |
| **median** | **46.8ms** | **94.8ms** | **+103% 악화** |
| **p90** | **115.3ms** | **302.5ms** | **+162% 악화** |
| **p95** | **154.6ms** | **382.9ms** | **+148% 악화** |

### aerospike-py gather mode

| Metric | baseline | pool 비활성화 | 변화 |
|--------|---------|--------------|------|
| avg | 68.9ms | 165.9ms | +141% 악화 |
| p90 | 128.8ms | 360.3ms | +180% 악화 |

### official-aerospike (참고, 영향 없음)

| Metric | baseline | pool 비활성화 | 변화 |
|--------|---------|--------------|------|
| avg (single) | 74.7ms | 176.5ms | +136% 악화 |
| avg (gather) | 86.9ms | 213.4ms | +146% 악화 |

**official-aerospike client 도 동일하게 악화 → 부하 자체가 더 걸린 것이 아니라 aerospike-py의 성능 저하가 전체 서버에 영향**

## 원인 분석

reference pool을 비활성화하면:
1. `pyo3_leak_on_drop_without_reference_pool`에 의해 `Py<T>` drop 시 **decref를 건너뜀** → 메모리 누수
2. Reference pool은 **batched decref** 역할 — GIL 획득 1회로 축적된 참조 카운트를 일괄 감소
3. 비활성화 시 개별 object마다 GIL 동기화 비용 발생, 또는 leak으로 GC 부하 증가

## 결론

**`pyo3_disable_reference_pool`은 적용하지 않음.** 성능이 2배 이상 악화됨.

PyO3 Performance Guide의 권장과 달리, async heavy workload에서는 reference pool의 batched decref가 오히려 성능에 유리함.
