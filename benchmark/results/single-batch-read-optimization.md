# single batch_read 최적화 테스트 결과

> 2026-04-16 | K8s 클러스터, benchmark namespace, 2 replicas

## 개요

`asyncio.gather(9 x batch_read)` 대신 9개 set의 key를 합쳐서 **1회 `batch_read()` 호출**로 변경.
`batch_read`가 이미 mixed-set key를 지원하므로 코드 변경만으로 적용 가능.

## 변경 내용

**파일**: `benchmark/src/serving/endpoints/predict.py`

```python
# Before: mode 기본값 "gather" (9회 호출)
mode: str = Query("gather", ...)

# After: mode 기본값 "single" (1회 호출)
mode: str = Query("single", ...)
```

**동작 차이**:
```python
# gather (9회 Rust 호출)
await asyncio.gather(*[client.batch_read(set_i_keys) for i in range(9)])
# → key_parse 9회 GIL 직렬화 + future_into_py 9회 + as_dict 9회

# single (1회 Rust 호출)
all_keys = flatten(keys_by_set)  # 9 set 합산
result = await client.batch_read(all_keys)
demux(result)  # Python에서 set별 분배
# → key_parse 1회 + future_into_py 1회 + as_dict 1회
```

## 병목 원인 (왜 single이 빠른가)

Rust 내부 구간별 실측 (`db_client_internal_stage_seconds`):

| Stage | 1회 호출 시간 | gather 9회 직렬 비용 | single 1회 비용 |
|-------|-------------|-------------------|----------------|
| key_parse (GIL) | 1.46ms | 9 × 1.46 = **13ms** | **~3ms** |
| io (네트워크) | 2.22ms | 병렬 = **2ms** | **2ms** |
| as_dict (GIL) | 0.79ms | 9 × 0.79 = **7ms** | **~3ms** |
| future_into_py 스케줄링 | ~5ms | 9 future = **~20ms** | **~5ms** |
| **합계** | | **~42ms** | **~13ms** |

**핵심**: GIL 직렬화(key_parse + as_dict) + future_into_py 스케줄링이 호출 횟수에 비례. single은 이를 1/9로 줄임.

## k6 테스트 조건

- K8s 클러스터, benchmark namespace, 2 replicas (4CPU/4Gi)
- Istio HTTPRoute 경유 (`aerospike-benchmark.example.com`)
- 10 VUs, 60초 steady-state
- Aerospike 8노드 (maiasp025-032:3000), namespace aidev
- 9 set × 200 keys per request, DLRM inference 포함

## k6 테스트 결과

### aerospike-py (핵심)

| Metric | gather | single | 개선 |
|--------|--------|--------|------|
| **avg** | 189ms | **126ms** | **-33%** |
| **median** | 176ms | **101ms** | **-43%** |
| **p90** | 393ms | **284ms** | **-28%** |
| **p95** | 434ms | **302ms** | **-30%** |
| min | 14ms | 16ms | (동등) |
| max | 617ms | 477ms | -23% |

### official-aerospike C client (참고)

| Metric | gather | single | 개선 |
|--------|--------|--------|------|
| **avg** | 251ms | **188ms** | **-25%** |
| **median** | 231ms | **192ms** | **-17%** |
| **p90** | 487ms | **369ms** | **-24%** |
| **p95** | 502ms | **396ms** | **-21%** |

### aerospike-py vs official-aerospike (single mode, 최종)

| Metric | official-aerospike | aerospike-py | speedup |
|--------|---------|----------|---------|
| **avg** | 188ms | **126ms** | **1.49x** |
| **median** | 192ms | **101ms** | **1.90x** |
| **p90** | 369ms | **284ms** | **1.30x** |
| **p95** | 396ms | **302ms** | **1.31x** |

## 최종 안정 테스트 (single 기본화 후 재실행)

single을 기본값으로 변경한 후 재실행한 결과:

### aerospike-py

| Metric | 값 |
|--------|---|
| **avg** | **60.8ms** |
| **median** | **46.8ms** |
| **p90** | **115.3ms** |
| **p95** | **154.6ms** |

### official-aerospike

| Metric | 값 |
|--------|---|
| avg | 74.7ms |
| median | 56.6ms |
| p90 | 149.1ms |
| p95 | 190.8ms |

### aerospike-py vs official-aerospike (최종)

| Metric | official-aerospike | aerospike-py | speedup |
|--------|---------|----------|---------|
| **avg** | 74.7ms | **60.8ms** | **1.23x** |
| **median** | 56.6ms | **46.8ms** | **1.21x** |
| **p90** | 149.1ms | **115.3ms** | **1.29x** |
| **p95** | 190.8ms | **154.6ms** | **1.23x** |

### Stress 테스트 (50 VUs ramp, single mode)

| Metric | aerospike-py |
|--------|---------|
| avg | 143.7ms |
| median | 99.3ms |
| p90 | 333.9ms |
| p95 | 405.3ms |
| 전체 requests | 15,084 |
| 성공률 | 99.99% |
| throughput | 56.9 req/s |

## Grafana 메트릭 (Prometheus datasource)

### Pipeline Breakdown (rate 5m)

| Stage | official-aerospike | aerospike-py | 비율 (aerospike-py) |
|-------|---------|----------|----------------|
| predict_duration (E2E) | 201ms | 152ms | 100% |
| batch_read_all | 162ms | 115ms | 75.5% |
| dlrm_inference | 16ms | 20ms | 13.4% |
| feature_extraction | 11ms | 12ms | 7.9% |
| key_extraction | 2ms | 2ms | 1.3% |
| response_build | 2ms | 2ms | 1.3% |

### Rust 내부 Stage (db_client_internal_stage_seconds)

| Stage | 시간 | 비율 |
|-------|------|------|
| key_parse | 1.46ms | 30.8% |
| io | 2.22ms | 46.8% |
| as_dict | 0.79ms | 16.6% |
| into_pyobject | 0.001ms | 0.03% |
| limiter_wait | 0.001ms | 0.01% |
| **합계** | **4.74ms** | |

## 결론

- **single 모드가 gather 대비 avg -33%, median -43% 개선**
- 원인: 9회 → 1회로 GIL 직렬화(key_parse + as_dict) + future_into_py 스케줄링 최소화
- `batch_read`가 이미 mixed-set key를 지원하므로 추가 API 변경 불필요
- 기본 mode를 `single`로 변경하여 적용 완료
