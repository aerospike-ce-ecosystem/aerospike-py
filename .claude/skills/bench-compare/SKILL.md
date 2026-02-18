---
name: bench-compare
description: Run benchmark comparison against official Aerospike C client
disable-model-invocation: true
---

# Benchmark Compare

aerospike-py와 공식 Aerospike C 클라이언트의 성능 비교를 실행합니다.

## 사전 조건

1. Aerospike 서버가 실행 중이어야 합니다.
2. 공식 C 클라이언트(`aerospike` PyPI 패키지)가 설치되어 있어야 합니다 (`bench` 의존성 그룹에 포함).

서버가 없으면 먼저 시작합니다:
```bash
make run-aerospike-ce
```

## 실행 단계

### 1. 서버 상태 확인
```bash
podman ps | grep aerospike || docker ps | grep aerospike
```

### 2. 빌드 (최신 코드 반영)
```bash
make build
```

### 3. 기본 벤치마크 실행
```bash
make run-benchmark
```

**기본 파라미터** (`Makefile` 기본값):
| 파라미터 | 환경변수 | 기본값 | 설명 |
|---------|---------|--------|------|
| 레코드 수 | `BENCH_COUNT` | 5000 | 테스트에 사용할 총 레코드 수 |
| 반복 횟수 | `BENCH_ROUNDS` | 20 | 각 연산의 측정 반복 횟수 |
| 동시성 | `BENCH_CONCURRENCY` | 50 | 동시 요청 수 |
| 배치 그룹 | `BENCH_BATCH_GROUPS` | 10 | 배치 연산 그룹 수 |
| 호스트 | `AEROSPIKE_HOST` | 127.0.0.1 | 서버 주소 |
| 포트 | `AEROSPIKE_PORT` | 18710 | 서버 포트 |

**커스텀 파라미터 예시:**
```bash
BENCH_COUNT=10000 BENCH_ROUNDS=10 BENCH_CONCURRENCY=100 make run-benchmark
```

### 4. 대규모 벤치마크 (선택)
```bash
make run-benchmark-large
```
100K ops, 5 rounds로 실행. 안정적인 성능 측정에 적합.

### 5. 벤치마크 리포트 생성 (선택)
```bash
make run-benchmark-report
```
JSON 파일 + 차트 이미지를 생성합니다.

### 6. NumPy 배치 벤치마크 (선택)
```bash
make run-numpy-benchmark
```

dict 기반 `batch_read` vs NumPy `batch_read_numpy` 성능 비교.

**NumPy 벤치마크 파라미터:**
| 파라미터 | 환경변수 | 기본값 |
|---------|---------|--------|
| 반복 횟수 | `NUMPY_BENCH_ROUNDS` | 10 |
| 동시성 | `NUMPY_BENCH_CONCURRENCY` | 50 |
| 배치 그룹 | `NUMPY_BENCH_BATCH_GROUPS` | 10 |

**NumPy 벤치마크 시나리오** (`--scenario` 옵션):
| 시나리오 | 설명 |
|---------|------|
| `record_scaling` | 레코드 수 변화에 따른 성능 (100, 500, 1K, 5K, 10K) |
| `bin_scaling` | bin 수 변화에 따른 성능 (1, 3, 5, 10, 20) |
| `post_processing` | 후처리 단계별 성능 (raw read -> column access -> filter -> aggregation) |
| `memory` | tracemalloc 기반 메모리 사용량 비교 |
| `all` | 전체 시나리오 (기본값) |

NumPy 리포트 생성:
```bash
make run-numpy-benchmark-report
```

## 벤치마크 방법론

`benchmark/bench_compare.py`의 측정 방법:
1. **Warmup phase** (500 ops): 연결 안정화, 결과 폐기
2. **Multiple rounds**: 각 연산을 `BENCH_ROUNDS` 회 반복, 라운드별 중앙값 측정
3. **Data pre-seeding**: 읽기 벤치마크 전 데이터 사전 생성
4. **GC disabled**: 측정 중 GC 비활성화
5. **Isolated key prefixes**: 각 클라이언트가 격리된 키 프리픽스 사용

## 결과 분석

벤치마크 결과를 분석하여 다음을 보고합니다:
- **연산별 비교**: sync put/get, async put/get, batch_read 등
- **Throughput**: ops/sec 비교
- **레이턴시**: 중앙값 (median of round medians) 비교
- **aerospike-py vs 공식 클라이언트 비율**: 몇 배 빠른지/느린지
- **이전 벤치마크 대비 성능 변화** (있는 경우)
- **성능 저하가 있는 경우 원인 분석 및 개선 제안**

## 벤치마크 실행 후 자동 정리

`make run-benchmark`, `make run-numpy-benchmark` 등 모든 벤치마크 Makefile 타겟은 실행 후 자동으로 `make stop-aerospike-ce`를 호출하여 컨테이너를 정리합니다.
