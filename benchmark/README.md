# aerospike-py vs 공식 aerospike client — uvicorn ASGI 벤치마크

uvicorn ASGI 위에서 **aerospike-py (Rust/PyO3 native async)** 와 **공식 aerospike Python client (C extension, sync → `run_in_executor` 래핑)** 의 성능을 시나리오별로 비교한다.

본 디렉토리는 메인 패키지와 독립된 별도 uv 프로젝트다. 메인 venv 와 섞이지 않는다.

---

## 시나리오

| # | 이름 | 엔드포인트 | 무엇을 측정하나 |
|---|---|---|---|
| **S1** | `read-only`        | `POST /s1/read`              | 순수 ASGI + `batch_read(N keys)` 라운드트립. 공식 client 의 `asyncio.to_thread` hop 비용이 가장 적나라하게 드러나는 baseline |
| **S2** | `dict-path infer`  | `POST /s2/predict`           | `batch_read` → Python dict 순회로 tensor build → DLRM(2-layer MLP, 64→256→1) forward |
| **S3** | `numpy-path infer` | `POST /s3/predict`           | aerospike-py: `to_numpy(dtype)` 구조화 배열 → `view(float32).reshape(-1, 64)` zero-copy → `torch.from_numpy`. 공식: 동일 결과를 dict로 받아 numpy 매트릭스 수동 채움 |
| **S4** | `gather vs single` | `POST /s4/gather` · `/single` | 같은 `n_groups × per_group` 키를 N개 `batch_read` 동시 호출 vs 단일 `batch_read` 로 합쳐 호출 |
| **S5** | `lazy subset`      | `POST /s5/subset`            | record당 64 bin 중 8개만 다운스트림 사용. aerospike-py: `to_numpy(subset_dtype)` 로 8개 컬럼만 materialize. 공식: `BatchRecord.record[2]` 가 항상 64개 전부 materialize 된 Python dict |

부가 변수: Python 런타임(`3.11` GIL vs `3.14t` free-threaded), uvicorn workers, batch size, concurrency.

---

## 사전 준비

| 도구 | 용도 | 설치 |
|---|---|---|
| `uv`                  | 의존성/런타임 관리   | `brew install uv` |
| `podman` 또는 `docker` | Aerospike CE 컨테이너 | `brew install podman && podman machine init && podman machine start` |
| `oha` (>= 1.14)       | HTTP 부하 생성       | `brew install oha` |
| Python 3.11           | baseline 런타임      | `uv python install 3.11` |
| Python 3.14t          | free-threaded 런타임 | `uv python install 3.14t` |

메인 패키지(`../`) 가 `maturin develop` 으로 빌드되어 있어야 `aerospike-py` import 가능. 미빌드라면 부모 디렉토리에서 `make build`.

---

## 실행

```bash
# 1) Aerospike CE 8.1.2.1_3 띄우기 (Docker Hub 공식 이미지, 포트 18710)
make up

# 2) 시드 데이터 적재 (test/bench 셋에 결정론적 키 N개)
make seed

# 3) 서버 띄우기 — 한 번에 하나만
make serve-py          # CLIENT=py    → aerospike-py AsyncClient
# 또는
make serve-official    # CLIENT=official → 공식 client + asyncio.to_thread

# 4) 한 시나리오 end-to-end 매트릭스 (서버 띄움/내림 + py/official 양쪽 oha)
make bench SCENARIO=s2 CONCURRENCY=10 DURATION=30s BATCH_SIZE=50

# 또는 6개 시나리오 변형 모두
make bench-all CONCURRENCY=10 DURATION=30s BATCH_SIZE=50

# 5) 결과 비교 표 생성
make report

# 6) 정리
make down
```

`make bench-all` 은 서버를 띄웠다 죽이는 매트릭스(클라이언트 × 런타임) 를 한 번에 돈다.

---

## 결과 위치

`results/<scenario>_<client>_<python>_<timestamp>/oha.json` 에 oha 원본 출력을 저장하고, `make report` 가 markdown 비교 표를 같은 디렉토리에 만든다. `results/` 는 gitignore.

---

## 무엇을 측정하지 않나

- OpenTelemetry / Prometheus / 사내 로깅: **측정 노이즈** + 사내 종속이라 의도적으로 제외. 필요해지면 별도 플래그 추가
- Docker 이미지 빌드 / k8s 배포: 로컬 벤치마크가 목적이라 제외
- `aerospike-py` Rust 내부 stage profiling: 메인 패키지의 `AEROSPIKE_PY_INTERNAL_METRICS=1` 환경변수로 가능 (별도)

---

## 포트 충돌 주의

`compose.yaml` 은 `127.0.0.1:18710` 을 점유한다. 메인 패키지의 `compose.local.yaml` 도 같은 포트를 쓰므로 **둘 중 하나만** 띄울 것.
