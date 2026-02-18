---
name: bench-compare
description: Run benchmark comparison against official Aerospike C client
disable-model-invocation: true
---

# Benchmark Compare

aerospike-py와 공식 Aerospike C 클라이언트의 성능 비교를 실행합니다.

## 사전 조건

Aerospike 서버가 실행 중이어야 합니다. 서버가 없으면 먼저 시작합니다:
```bash
make run-aerospike-ce
```

## 실행 단계

### 1. 서버 상태 확인
```bash
docker ps | grep aerospike || podman ps | grep aerospike
```

### 2. 빌드 (최신 코드 반영)
```bash
make build
```

### 3. 벤치마크 실행
```bash
make run-benchmark
```

환경변수로 벤치마크 파라미터를 조정할 수 있습니다:
- `BENCH_COUNT`: 레코드 수 (기본: 1000)
- `ROUNDS`: 반복 횟수 (기본: 3)
- `CONCURRENCY`: 동시성 레벨 (기본: 10)

### 4. NumPy 배치 벤치마크 (선택)
```bash
make run-numpy-benchmark
```

## 결과 분석

벤치마크 결과를 분석하여 다음을 보고합니다:
- Sync/Async 각각의 throughput 비교
- 레이턴시 (p50, p95, p99) 비교
- 이전 벤치마크 대비 성능 변화 (있는 경우)
- 성능 저하가 있는 경우 원인 분석 및 개선 제안
