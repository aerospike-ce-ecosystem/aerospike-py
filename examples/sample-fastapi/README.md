# sample-fastapi

FastAPI + `aerospike-py` AsyncClient 를 사용한 CRUD 예제 프로젝트입니다.

## 구조

```
sample-fastapi/
├── app/
│   ├── main.py          # FastAPI 앱, lifespan (클라이언트 생명주기)
│   ├── config.py         # pydantic-settings 기반 설정
│   ├── models.py         # Pydantic 요청/응답 모델
│   └── routers/
│       └── users.py      # User CRUD 엔드포인트
├── docker-compose.yaml   # 로컬 Aerospike 서버
└── pyproject.toml
```

## 실행 방법

### 1. Aerospike 서버 시작

```bash
docker compose up -d
```

### 2. 의존성 설치

```bash
pip install -e .
```

### 3. 서버 실행

```bash
uvicorn app.main:app --reload
```

서버가 시작되면 http://localhost:8000/docs 에서 Swagger UI를 확인할 수 있습니다.

## API 엔드포인트

| Method   | Path             | 설명             |
|----------|------------------|------------------|
| `GET`    | `/health`        | 헬스 체크        |
| `POST`   | `/users`         | 유저 생성        |
| `GET`    | `/users`         | 전체 유저 조회   |
| `GET`    | `/users/{id}`    | 유저 단건 조회   |
| `PUT`    | `/users/{id}`    | 유저 수정        |
| `DELETE` | `/users/{id}`    | 유저 삭제        |

## 사용 예시

```bash
# 유저 생성
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'

# 전체 유저 조회
curl http://localhost:8000/users

# 유저 수정
curl -X PUT http://localhost:8000/users/{user_id} \
  -H "Content-Type: application/json" \
  -d '{"age": 31}'

# 유저 삭제
curl -X DELETE http://localhost:8000/users/{user_id}
```

## 환경 변수

| 변수                     | 기본값       | 설명                    |
|--------------------------|-------------|------------------------|
| `APP_AEROSPIKE_HOST`     | `127.0.0.1` | Aerospike 호스트       |
| `APP_AEROSPIKE_PORT`     | `3000`      | Aerospike 포트         |
| `APP_AEROSPIKE_NAMESPACE`| `test`      | 사용할 namespace       |
| `APP_AEROSPIKE_SET`      | `users`     | 사용할 set 이름        |
