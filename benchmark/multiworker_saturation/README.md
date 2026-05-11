# Multi-worker saturation reproducer

Issue [#347](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/347) — production multi-worker + CPU-bound 환경에서 aerospike-py가 aerospike-client-python (C ext) 대비 saturation point에서 RPS/core 2.4× 비효율적이라고 보고됨.

이 reproducer는 그 환경을 로컬 macOS + Podman으로 모사한다.

## 모사 대상 (이슈 환경)

| 항목 | Production (이슈) | 본 reproducer |
|---|---|---|
| pod CPU limit | 8 core × 3 pod | Podman container `--cpus 8` × 1 |
| uvicorn workers | 8 / pod | 8 (단일 container) |
| 요청당 batch_read 수 | 9 FV (gather) | 9 FV (asyncio.gather) |
| 요청당 총 키 수 | 720 (80/FV × 9) | 720 (동일) |
| CPU-bound co-resident | DLRM inference (PyTorch) | NumPy matmul stub (GIL 압력 모사) |
| Load tool | k6 (parallelism=4) | k6 (단일 runner) |
| 부하 단계 | VU 100, 150 | VU 10/50/100/150/200 ramp |

DLRM/PyTorch 부재는 GIL 압력을 약화시킬 수 있음 — Phase 0 게이트에서 정성적 재현(패턴 동일성)으로 판정.

## 비교축

4-cell matrix:

|  | Python 3.11 + GIL | Python 3.14t free-threaded |
|---|---|---|
| **aerospike-py** | cell A1 | cell A2 |
| **aerospike-client-python** (C ext, `run_in_executor`) | cell B1 | cell B2 |

## 측정 지표

- RPS (k6 `iteration_duration` + `http_reqs/s`)
- p50 / p95 / p99 endpoint latency
- Container CPU% (`podman stats` 1초 폴링)
- Container RSS (동일)
- GIL wait % (`py-spy --gil` 60s sampling)
- **RPS / CPU-core** — 가장 중요한 정규화 지표
- aerospike-py stage profiling 11개 (`AEROSPIKE_PY_INTERNAL_METRICS=1`):
  - `key_parse`, `future_into_py_setup`, `tokio_schedule_delay`, `limiter_wait`,
    `io`, `spawn_blocking_delay`, `into_pyobject`, `event_loop_resume_delay`,
    `as_dict`, `merge_as_dict`

## 실행

```bash
# 1. Aerospike CE 기동 (host-side, 다른 터미널)
cd ../..
make run-aerospike-ce

# 2. release build of aerospike-py (Phase 0 baseline용)
make build

# 3. seed 데이터 로드 (9 set × 1000 keys/set)
cd benchmark/multiworker_saturation
uv run python -m app.seed

# 4. 단일 cell 측정
./scripts/run.sh --client aerospike-py --python 3.11
./scripts/run.sh --client legacy --python 3.11
./scripts/run.sh --client aerospike-py --python 3.14t
./scripts/run.sh --client legacy --python 3.14t

# 5. 결과 합치기
uv run python scripts/compose_report.py results/saturation_baseline_*/
```

## 게이트 (Phase 0 → Phase 1 진입 조건)

모두 만족해야 Phase 1 진입:

1. VU 100 지점 — 두 클라이언트 endpoint p95 동등 (±10%), container CPU% 격차 ≥ 30%p
2. VU 150 지점 — aerospike-py RPS가 C ext 대비 ≥ 30% 낮음 (collapse 확인)
3. VU 100에서 stage profiling: `key_parse + future_into_py_setup + into_pyobject` 합이 endpoint p95의 ≥ 15%

미충족 시 plan 중단, 이슈 #347에 코멘트 게시.

## 결과 위치

`results/saturation_<date>/` — 자동 timestamped. 각 cell당:
- `<cell>.json` — k6 metrics + podman stats summary
- `<cell>.stage_profile.json` — stage profiling
- `<cell>.gil_wait.txt` — py-spy GIL sampling
- `report.md` — 사람이 읽는 요약
