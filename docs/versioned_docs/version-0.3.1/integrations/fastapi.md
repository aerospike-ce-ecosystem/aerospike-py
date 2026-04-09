---
title: FastAPI Integration
sidebar_label: FastAPI
sidebar_position: 1
description: AsyncClient with FastAPI lifespan and dependency injection.
---

## Prerequisites

```bash
pip install fastapi uvicorn pydantic-settings aerospike-py
```

## Lifespan Management

```python
from contextlib import asynccontextmanager

import aerospike_py
from aerospike_py import AsyncClient
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "policies": {"key": aerospike_py.POLICY_KEY_SEND},
    })
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)
```

## Dependency Injection

```python
from aerospike_py import AsyncClient
from fastapi import Request


def get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike
```

## Configuration

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 3000
    aerospike_namespace: str = "test"
    aerospike_set: str = "users"

    model_config = {"env_prefix": "APP_"}
```

## CRUD Endpoint Example

```python
import uuid

from aerospike_py import AsyncClient
from aerospike_py.exception import RecordNotFound
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

NS, SET = "test", "users"
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


def _client(request: Request) -> AsyncClient:
    return request.app.state.aerospike


def _key(user_id: str) -> tuple[str, str, str]:
    return (NS, SET, user_id)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, request: Request):
    client = _client(request)
    user_id = uuid.uuid4().hex
    await client.put(_key(user_id), body.model_dump())
    _, meta, bins = await client.get(_key(user_id))
    return UserResponse(user_id=user_id, generation=meta.gen, **bins)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    client = _client(request)
    try:
        _, meta, bins = await client.get(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(user_id=user_id, generation=meta.gen, **bins)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, request: Request):
    client = _client(request)
    try:
        await client.remove(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found")
```

## Full Example

The [`examples/sample-fastapi/`](https://github.com/KimSoungRyoul/aerospike-py/tree/main/examples/sample-fastapi) directory contains a complete application with 11 routers, Pydantic models, Docker Compose setup, and tests.

```bash
cd examples/sample-fastapi
docker compose up -d
pip install -r requirements.txt
uvicorn app.main:app --reload
# Visit http://localhost:8000/docs
```
