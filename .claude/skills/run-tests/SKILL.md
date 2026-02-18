---
name: run-tests
description: Build, ensure Aerospike server is healthy, and run tests
disable-model-invocation: true
args: "[test-type]"
---

# Run Tests

aerospike-py 테스트를 실행합니다. Aerospike 서버가 필요한 테스트는 자동으로 컨테이너를 시작하고 health check를 통과한 후 실행합니다.

## 인자

`/run-tests [test-type]` 형식으로 호출합니다.

| test-type | 서버 필요 | 설명 |
|-----------|----------|------|
| `unit` | No | 유닛 테스트 (기본값) |
| `integration` | Yes | 통합 테스트 |
| `concurrency` | Yes | 스레드/async 안전성 테스트 |
| `compat` | Yes | 공식 C 클라이언트 호환성 테스트 |
| `all` | Yes | 전체 테스트 |
| `matrix` | No | Python 3.10~3.14 매트릭스 테스트 |

인자가 없으면 `unit`을 실행합니다.

## 실행 단계

### 1. 빌드
```bash
make build
```

### 2. Aerospike 서버 보장 (unit, matrix 제외)

`unit`과 `matrix`는 서버가 필요 없으므로 이 단계를 건너뜁니다.
나머지 테스트 타입은 아래 순서로 서버를 보장합니다:

#### 2-1. 컨테이너 실행 확인
```bash
podman compose -f compose.local.yaml up -d
```

#### 2-2. Health check (최대 30초 대기)
```bash
for i in $(seq 1 30); do
  if podman exec aerospike asinfo -v status 2>/dev/null | grep -q 'ok'; then
    echo "Aerospike is ready"
    break
  fi
  echo "Waiting for Aerospike... ($i/30)"
  sleep 1
done
```

health check가 30초 안에 통과하지 못하면 `podman logs aerospike`로 로그를 확인하고 원인을 보고합니다.

### 3. 테스트 실행

인자에 따라 해당 Makefile 타겟을 실행합니다:

| 인자 | 명령어 |
|------|--------|
| `unit` | `uv run pytest tests/unit/ -v` |
| `integration` | `uvx --with tox-uv tox -e integration` |
| `concurrency` | `uvx --with tox-uv tox -e concurrency` |
| `compat` | `uvx --with tox-uv tox -e compat` |
| `all` | `uvx --with tox-uv tox -e all` |
| `matrix` | `uvx --with tox-uv tox` |

### 4. 결과 보고
- 통과한 테스트 수 / 실패한 테스트 수 요약
- 실패한 테스트가 있으면 에러 메시지와 원인 분석
