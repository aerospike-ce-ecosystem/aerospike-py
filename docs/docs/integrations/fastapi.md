---
title: FastAPI Integration
sidebar_label: FastAPI
sidebar_position: 1
description: How to use aerospike-py AsyncClient with FastAPI lifespan and dependency injection.
---

## Prerequisites

```bash
pip install fastapi uvicorn pydantic-settings aerospike-py
```

## Lifespan Management

Use FastAPI's `lifespan` to create and close `AsyncClient` alongside the application:

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

`app.state.aerospike` stores the client so any request handler or dependency can access it.

## Dependency Injection

Create a reusable dependency that extracts the client from `app.state`:

```python
from aerospike_py import AsyncClient
from fastapi import Request


def get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike
```

## Configuration with pydantic-settings

Externalize connection parameters via environment variables:

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

Set `APP_AEROSPIKE_HOST`, `APP_AEROSPIKE_PORT`, etc. to override defaults.

## CRUD Endpoint Example

A minimal user CRUD router using `AsyncClient`:

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

## Full Example Project

The [`examples/sample-fastapi/`](https://github.com/KimSoungRyoul/aerospike-py/tree/main/examples/sample-fastapi) directory contains a complete FastAPI application with:

- 11 routers covering records, batch, operations, indexes, UDF, admin, and more
- Pydantic models for request/response validation
- Docker Compose setup for local Aerospike
- Test suite with `pytest` + `httpx`

```bash
cd examples/sample-fastapi
docker compose up -d      # start Aerospike
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for the interactive Swagger UI.
