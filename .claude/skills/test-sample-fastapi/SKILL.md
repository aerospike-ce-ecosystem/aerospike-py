---
name: test-sample-fastapi
description: Build aerospike-py and run sample-fastapi integration tests to verify changes work in a real FastAPI application
disable-model-invocation: true
---

# Test Sample FastAPI

aerospike-py에 변경사항이 생겼을 때, 로컬에서 빌드 후 sample-fastapi 앱이 정상 동작하는지 검증합니다.

## 실행 단계

### 1. aerospike-py 빌드
프로젝트 루트에서 Rust 네이티브 모듈을 빌드합니다:
```bash
cd /Users/ksr/github/aerospike-py && uv run maturin develop --release
```
빌드 실패 시 에러를 분석하고 수정 방향을 제안하세요.

### 2. sample-fastapi 의존성 동기화
빌드된 aerospike-py를 sample-fastapi에 반영합니다:
```bash
cd /Users/ksr/github/aerospike-py/examples/sample-fastapi && uv sync --extra dev
```
`pyproject.toml`의 `[tool.uv.sources]`에 `aerospike-py = { path = "../.." }`로 로컬 경로가 설정되어 있으므로, 방금 빌드한 패키지가 자동으로 사용됩니다.

### 3. Aerospike 서버 확인
로컬 Aerospike 서버가 실행 중인지 확인합니다:
```bash
docker ps | grep aerospike || podman ps | grep aerospike
```
- 실행 중이면 그대로 진행
- 실행 중이 아니면 TestContainers가 자동으로 컨테이너를 생성하므로 Docker/Podman 데몬이 실행 중인지만 확인

### 4. 테스트 실행
sample-fastapi 테스트를 실행합니다:
```bash
cd /Users/ksr/github/aerospike-py/examples/sample-fastapi && uv run pytest tests/ -v
```

### 5. 결과 보고
- 모든 테스트 통과 시: 변경사항이 FastAPI 앱에서 정상 동작함을 확인
- 실패한 테스트가 있으면:
  - 실패한 테스트 이름과 에러 메시지를 정리
  - aerospike-py 변경사항과의 관계 분석
  - 수정 방향 제안 (aerospike-py 쪽 문제인지, sample-fastapi 쪽 문제인지 구분)
