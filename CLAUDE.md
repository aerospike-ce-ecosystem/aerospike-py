# aerospike-py

Aerospike NoSQL 데이터베이스를 위한 Python 클라이언트 라이브러리.
**Rust(PyO3)로 작성**되어 네이티브 바이너리로 컴파일되며, Python에서 sync/async 양쪽 API를 제공한다.

## 설치

```bash
pip install aerospike-py
```

> Python 3.10~3.14 (3.14t free-threaded 포함), CPython 전용. macOS(arm64, x86_64) 및 Linux(x86_64, aarch64) 지원.

## 프로젝트 구조

```
aerospike-py/
├── rust/src/               # Rust 네이티브 모듈 (PyO3 바인딩)
│   ├── client.rs           # Sync Client 구현
│   ├── async_client.rs     # Async Client 구현
│   ├── errors.rs           # 에러 매핑 (Aerospike → Python 예외)
│   ├── operations.rs       # operate/operate_ordered 연산 변환
│   ├── query.rs            # Query 객체
│   ├── constants.rs        # 상수 정의
│   ├── expressions.rs      # Expression 필터 파싱
│   ├── metrics.rs          # Prometheus 메트릭 수집
│   ├── tracing.rs          # OpenTelemetry 트레이싱
│   ├── policy/             # 정책 파싱 (read, write, admin, batch, query, client)
│   └── types/              # 타입 변환 (key, value, record, bin, host)
├── src/aerospike_py/       # Python 패키지
│   ├── __init__.py         # Client/AsyncClient 래퍼, 팩토리 함수, 상수 re-export
│   ├── __init__.pyi        # Type stubs
│   ├── exception.py        # 예외 클래스 re-export
│   ├── predicates.py       # 쿼리 프레디케이트 헬퍼
│   ├── list_operations.py  # List CDT 연산 헬퍼
│   ├── map_operations.py   # Map CDT 연산 헬퍼
│   ├── exp.py              # Expression 필터 빌더
│   └── numpy_batch.py      # NumPy 기반 배치 결과
├── tests/
│   ├── unit/               # 유닛 테스트 (서버 불필요)
│   ├── integration/        # 통합 테스트 (Aerospike 서버 필요)
│   ├── concurrency/        # 스레드 안전성 테스트
│   ├── compatibility/      # 공식 C 클라이언트 호환성 테스트
│   └── feasibility/        # 프레임워크 통합 테스트 (FastAPI, Gunicorn)
└── pyproject.toml          # 빌드 설정 (maturin)
```

## 개발 환경

패키지 매니저로 **uv**를 사용한다. Makefile에 주요 명령어가 정의되어 있다.

```bash
# 의존성 설치
make install                        # uv sync --all-groups

# Rust 빌드
make build                          # uv run maturin develop --release
cargo check --manifest-path rust/Cargo.toml  # 컴파일 체크만 (빠름)

# 테스트
make test-unit                      # 유닛 테스트 (서버 불필요)
make test-integration               # 통합 테스트 (Aerospike 서버 필요)
make test-concurrency               # 스레드 안전성 테스트
make test-compat                    # 공식 클라이언트 호환성 테스트
make test-all                       # 전체 테스트
make test-matrix                    # Python 3.10~3.14 매트릭스 테스트 (tox)

# 린트 & 포맷
make lint                           # ruff check + clippy
make fmt                            # ruff format + cargo fmt

# 로컬 Aerospike 서버
make run-aerospike-ce               # compose.local.yaml로 Aerospike CE 실행 (port 18710)

# 벤치마크
make run-benchmark                  # aerospike-py vs 공식 클라이언트 비교
make run-numpy-benchmark            # NumPy 배치 벤치마크
```

### Pre-commit Hooks

커밋 시 자동 실행: trailing-whitespace, ruff format/lint, pyright, cargo fmt, cargo clippy (-D warnings)

### 주의사항

- OpenTelemetry(`otel`)은 기본 빌드에 항상 포함됨 (별도 feature flag 불필요)
- 통합 테스트 실행 전 `make run-aerospike-ce`로 로컬 서버 필요
- maturin 버전 `>=1.9,<2.0`으로 고정
- `AEROSPIKE_HOST`, `AEROSPIKE_PORT` 환경변수로 서버 주소 변경 가능 (기본: `127.0.0.1:18710`)
- `RUNTIME` 환경변수로 docker/podman 선택 가능 (기본: podman)
- 컨테이너 설정은 프로젝트 루트의 compose 파일로 관리: `compose.local.yaml` (개발용), `compose.sample-fastapi.yaml` (FastAPI 예제용)
- CI는 자체 서비스 컨테이너(port 3000)를 사용하며 `AEROSPIKE_PORT=3000` 환경변수로 설정됨

## API 레퍼런스

API 사용법(메서드 시그니처, 타입, 상수, 예외, 코드 예제)은 `.claude/skills/aerospike-py/SKILL.md` 참조.
전체 타입/상수 정의는 `src/aerospike_py/__init__.pyi` 참조.

---

## 테스트 설정

통합 테스트에는 Aerospike 서버가 필요하다. `tests/__init__.py`에서 기본 설정:

```python
AEROSPIKE_CONFIG = {"hosts": [("127.0.0.1", 18710)], "cluster_name": "docker"}
```

```bash
make run-aerospike-ce               # 로컬 Aerospike 서버 실행
make test-unit                      # 서버 없이 실행 가능
make test-integration               # 서버 필요
```

주요 fixture (`tests/conftest.py`):
- `client` — module-scoped sync 클라이언트
- `async_client` — function-scoped async 클라이언트
- `cleanup` / `async_cleanup` — 테스트 후 자동 레코드 정리

pytest 설정: `asyncio_mode = "auto"` (async 테스트 자동 감지)
