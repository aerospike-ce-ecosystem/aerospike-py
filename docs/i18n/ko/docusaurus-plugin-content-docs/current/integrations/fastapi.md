---
title: FastAPI 연동
sidebar_label: FastAPI
sidebar_position: 1
description: aerospike-py AsyncClient를 FastAPI lifespan 및 의존성 주입과 함께 사용하는 방법.
---

## 사전 준비

```bash
pip install fastapi uvicorn pydantic-settings aerospike-py
```

## Lifespan 관리

FastAPI의 `lifespan`을 사용하여 애플리케이션과 함께 `AsyncClient`를 생성하고 종료합니다:

```python
from contextlib import asynccontextmanager

import aerospike_py
from aerospike_py import AsyncClient
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncClient(
        {
            "hosts": [("127.0.0.1", 3000)],
            "policies": {"key": aerospike_py.POLICY_KEY_SEND},
        }
    )
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)
```

`app.state.aerospike`에 클라이언트를 저장하여 모든 요청 핸들러나 의존성에서 접근할 수 있습니다.

## 의존성 주입

`app.state`에서 클라이언트를 추출하는 재사용 가능한 의존성을 만듭니다:

```python
from aerospike_py import AsyncClient
from fastapi import Request


def get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike
```

## pydantic-settings를 활용한 설정

환경 변수를 통해 연결 파라미터를 외부화합니다:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 3000
    aerospike_namespace: str = "test"
    aerospike_set: str = "users"

    model_config = {"env_prefix": "APP_"}


settings = Settings()
```

`APP_AEROSPIKE_HOST`, `APP_AEROSPIKE_PORT` 등을 설정하여 기본값을 재정의할 수 있습니다.

## CRUD 엔드포인트 예제

`AsyncClient`를 사용한 간단한 사용자 CRUD 라우터입니다:

```python
import uuid

from aerospike_py import AsyncClient
from aerospike_py.exception import RecordNotFound
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

NS = "test"
SET = "users"

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    email: str
    age: int = Field(..., ge=0, le=200)


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    age: int
    generation: int


def _get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike


def _key(user_id: str) -> tuple[str, str, str]:
    return (NS, SET, user_id)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, request: Request):
    client = _get_client(request)
    user_id = uuid.uuid4().hex
    await client.put(_key(user_id), body.model_dump())
    _, meta, bins = await client.get(_key(user_id))
    return UserResponse(user_id=user_id, generation=meta.gen, **bins)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    client = _get_client(request)
    try:
        _, meta, bins = await client.get(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(user_id=user_id, generation=meta.gen, **bins)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, request: Request):
    client = _get_client(request)
    try:
        await client.remove(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found")
```

## 전체 예제 프로젝트

[`examples/sample-fastapi/`](https://github.com/KimSoungRyoul/aerospike-py/tree/main/examples/sample-fastapi) 디렉토리에 완전한 FastAPI 애플리케이션이 포함되어 있습니다:

- 레코드, 배치, 오퍼레이션, 인덱스, UDF, 관리 등 11개 라우터
- 요청/응답 검증을 위한 Pydantic 모델
- 로컬 Aerospike를 위한 Docker Compose 설정
- `pytest` + `httpx` 테스트 코드

```bash
cd examples/sample-fastapi
docker compose up -d      # Aerospike 시작
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`http://localhost:8000/docs`에서 Swagger UI를 확인할 수 있습니다.
