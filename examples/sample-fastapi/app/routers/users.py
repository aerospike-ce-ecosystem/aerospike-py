from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from aerospike_py import AsyncClient
from aerospike_py.exception import RecordNotFound
from app.config import settings
from app.dependencies import get_client
from app.models import MessageResponse, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

NS = settings.aerospike_namespace
SET = settings.aerospike_set


def _key(user_id: str) -> tuple[str, str, str]:
    return (NS, SET, user_id)


def _to_response(user_id: str, meta: dict, bins: dict) -> UserResponse:
    return UserResponse(
        user_id=user_id,
        name=bins["name"],
        email=bins["email"],
        age=bins["age"],
        generation=meta.gen,
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, client: AsyncClient = Depends(get_client)):
    """Create a new user."""
    user_id = uuid.uuid4().hex
    key = _key(user_id)

    bins = {"user_id": user_id, **body.model_dump()}
    await client.put(key, bins)

    _, meta, bins = await client.get(key)
    return _to_response(user_id, meta, bins)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, client: AsyncClient = Depends(get_client)):
    """Get a user by ID."""
    try:
        _, meta, bins = await client.get(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None
    return _to_response(user_id, meta, bins)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, body: UserUpdate, client: AsyncClient = Depends(get_client)):
    """Update an existing user (partial update)."""
    key = _key(user_id)

    # Verify the record exists first
    try:
        await client.get(key)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None

    update_bins = body.model_dump(exclude_none=True)
    if not update_bins:
        raise HTTPException(status_code=422, detail="No fields to update")

    await client.put(key, update_bins)

    _, meta, bins = await client.get(key)
    return _to_response(user_id, meta, bins)


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(user_id: str, client: AsyncClient = Depends(get_client)):
    """Delete a user by ID."""
    try:
        await client.remove(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None
    return MessageResponse(message=f"User {user_id} deleted")


@router.get("", response_model=list[UserResponse])
async def list_users(client: AsyncClient = Depends(get_client)):
    """List all users by scanning the set via query().results()."""
    records = await client.query(NS, SET).results()
    result = []
    for key, meta, bins in records:
        if bins is None:
            continue
        # query()는 aerospike-core 알파 제한으로 user_key=None을 반환하므로
        # 생성 시 bins에 저장한 user_id를 우선 사용한다.
        user_id = bins.get("user_id") or (key[2] if key else None)
        if user_id is None or not isinstance(bins.get("name"), str):
            continue
        result.append(_to_response(str(user_id), meta, bins))
    return result
