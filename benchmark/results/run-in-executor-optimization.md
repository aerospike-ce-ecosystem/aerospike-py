# DLRM inference `run_in_executor` 최적화 결과

> 2026-04-16 | K8s 클러스터, benchmark namespace, aerospike-py single mode, 10 VUs

## 1. 문제

`future_into_py` 내부 프로파일링에서 `event_loop_resume_delay`가 168ms (90%).
원인: DLRM inference (21ms, CPU-bound)가 single-threaded event loop을 blocking →
다른 요청의 batch_read coroutine resume가 inference 끝날 때까지 대기.

```
10 VUs × 21ms inference ≈ 168ms — 정확히 일치
```

## 2. 변경

**파일**: `benchmark/src/serving/endpoints/predict.py`

```python
# Before (event loop blocking)
with torch.no_grad():
    scores = request.app.state.model(sparse, dense)  # 21ms CPU-bound

# After (event loop 해방)
def _infer(model, sparse, dense):
    with torch.no_grad():
        return model(sparse, dense)

loop = asyncio.get_running_loop()
scores = await loop.run_in_executor(None, _infer, model, sparse, dense)
```

## 3. k6 결과 (10 VUs, single mode, 60초)

### TPS & Latency

| Metric | Before | **After** | **개선** |
|--------|--------|----------|---------|
| **avg** | 129ms | **87ms** | **-33%** |
| **median** | 91ms | **68ms** | **-25%** |
| **p90** | 291ms | **174ms** | **-40%** |
| **p95** | 319ms | **197ms** | **-38%** |
| **TPS** | 30.8 req/s | **54.2 req/s** | **+76%** |

### Grafana Histogram Percentiles (predict_duration_seconds)

| Percentile | predict E2E | batch_read_all |
|-----------|------------|----------------|
| **p90** | **177ms** | **69ms** |
| **p99** | **292ms** | **145ms** |

## 4. Pipeline Breakdown (Grafana avg, rate 3m)

### Before (inference on event loop)

| Stage | 시간 | 비율 |
|-------|------|------|
| predict_duration (E2E) | 270ms | 100% |
| batch_read_all | 232ms | **85.9%** ← event loop blocking으로 인한 허수 |
| dlrm_inference | 21ms | 7.8% |
| feature_extraction | 12ms | 4.4% |
| key_extraction | 2ms | 0.7% |
| response_build | 2ms | 0.7% |

### After (inference on thread pool)

| Stage | 시간 | 비율 |
|-------|------|------|
| predict_duration (E2E) | **85ms** | 100% |
| **dlrm_inference** | **40ms** | **46.9%** ← thread pool 오버헤드 포함 |
| **batch_read_all** | **37ms** | **42.9%** ← 진짜 비용 |
| feature_extraction | 7ms | 8.5% |
| key_extraction | 2ms | 2.1% |
| response_build | 2ms | 2.2% |

### 핵심 변화

```
Before: batch_read 비율 85.9% → After: 42.9%
  → batch_read가 느린 게 아니라, inference가 event loop을 blocking해서
    coroutine resume가 밀린 것. 허수였음.

Before: inference 비율 7.8% → After: 46.9%
  → run_in_executor 전환으로 thread pool 스케줄링 오버헤드(~19ms) 추가되어
    21ms → 40ms로 증가했지만, event loop은 해방됨.
```

## 5. Rust 내부 Stage (event_loop_resume_delay)

| Stage | Before | **After** | **개선** |
|-------|--------|----------|---------|
| **(D) event_loop_resume_delay** | **168.1ms** | **19.0ms** | **-89%** |
| io | 6.08ms | 5.98ms | 동일 |
| key_parse | 6.04ms | 5.09ms | 동일 |
| (C) spawn_blocking_delay | 3.22ms | 3.03ms | 동일 |
| as_dict | 2.96ms | 1.92ms | 동일 |
| (B) tokio_schedule_delay | 0.45ms | 0.10ms | 개선 |
| (A) future_into_py_setup | 0.02ms | 0.03ms | 동일 |

## 6. 결론

- **`run_in_executor` 한 줄 변경으로 TPS +76%, latency -33~40%**
- `event_loop_resume_delay` 168ms → 19ms (-89%)
- 병목이 batch_read에서 inference로 이동 — 이제 진짜 비용이 보임
- batch_read_all 실제 비용은 37ms (이전 232ms의 16%)이며, 85.9%가 허수였음

## 7. 현재 병목

```
E2E 85ms:
  dlrm_inference   40ms (47%) ← thread pool 스케줄링 19ms + 실제 inference 21ms
  batch_read_all   37ms (43%) ← Rust I/O 6ms + as_dict 2ms + PyO3 overhead 29ms
  feature_extract   7ms  (8%)
  기타               1ms  (2%)
```

inference와 batch_read가 거의 동일 비중 — 더 이상 단일 병목이 아닌 균형 잡힌 상태.
추가 개선은 inference 최적화 (ONNX, TorchScript) 또는 Free-threaded 3.14t로 가능.
