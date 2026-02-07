# Contributing

aerospike-py에 기여해 주셔서 감사합니다!

## Development Setup

### Prerequisites

- Python 3.10+
- Rust 툴체인 ([rustup](https://rustup.rs/))
- Docker (테스트용 Aerospike 서버)

### Setup

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv
source .venv/bin/activate

# 개발 의존성 설치
pip install maturin pytest pytest-asyncio ruff

# Rust 확장 빌드
maturin develop
```

### Start Aerospike Server

```bash
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 \
  -e "NAMESPACE=test" \
  -e "CLUSTER_NAME=docker" \
  aerospike/aerospike-server
```

## Running Tests

```bash
# 전체 테스트
pytest

# 특정 테스트 파일
pytest tests/test_client.py

# 특정 테스트
pytest tests/test_client.py::test_put_get -v
```

## Code Style

프로젝트는 Python 코드에 [Ruff](https://docs.astral.sh/ruff/)를 사용합니다.

```bash
# Lint
ruff check .

# 포맷
ruff format .
```

Rust 코드:

```bash
cd rust
cargo fmt
cargo clippy
```

## Project Structure

```
aerospike-py/
├── rust/src/              # PyO3 Rust Bindings
│   ├── client.rs          # Sync Client
│   ├── async_client.rs    # Async Client
│   ├── query.rs           # Query / Scan
│   ├── operations.rs      # 연산 매핑 (CDT list/map 포함)
│   ├── expressions.rs     # Expression 필터 컴파일
│   ├── errors.rs          # Error → Exception 매핑
│   ├── constants.rs       # 130+ 상수
│   ├── types/             # 타입 변환기
│   └── policy/            # 정책 파서
├── src/aerospike_py/      # Python 패키지
│   ├── __init__.py        # Re-exports, Client 래퍼
│   ├── exp.py             # Expression 필터 빌더
│   ├── list_operations.py # List CDT 연산 헬퍼
│   ├── map_operations.py  # Map CDT 연산 헬퍼
│   ├── exception.py       # Exception 계층
│   └── predicates.py      # 쿼리 Predicates
└── tests/                 # 단위 + 통합 테스트
```

## Pull Request Guidelines

1. 기존 코드 스타일을 따라주세요
2. 새 기능에 대한 테스트를 추가해 주세요
3. 모든 테스트가 통과하는지 확인해 주세요
4. PR 설명에 변경 사항을 명확히 기술해 주세요

## Reporting Issues

버그 리포트나 기능 요청은 [GitHub Issues](https://github.com/KimSoungRyoul/aerospike-py/issues)에 올려주세요.
