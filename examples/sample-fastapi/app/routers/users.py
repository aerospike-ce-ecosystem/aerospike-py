from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from aerospike_py import AsyncClient
from aerospike_py.exception import RecordNotFound
from app.config import settings
from app.models import MessageResponse, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

NS = settings.aerospike_namespace
SET = settings.aerospike_set


def _get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike


def _key(user_id: str) -> tuple[str, str, str]:
    return (NS, SET, user_id)


def _to_response(user_id: str, meta: dict, bins: dict) -> UserResponse:
    return UserResponse(
        user_id=user_id,
        name=bins["name"],
        email=bins["email"],
        age=bins["age"],
        generation=meta["gen"],
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, request: Request):
    """Create a new user."""
    client = _get_client(request)
    user_id = uuid.uuid4().hex
    key = _key(user_id)

    bins = body.model_dump()
    await client.put(key, bins)

    _, meta, bins = await client.get(key)
    return _to_response(user_id, meta, bins)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    """Get a user by ID."""
    client = _get_client(request)
    try:
        _, meta, bins = await client.get(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None
    return _to_response(user_id, meta, bins)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, body: UserUpdate, request: Request):
    """Update an existing user (partial update)."""
    client = _get_client(request)
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
async def delete_user(user_id: str, request: Request):
    """Delete a user by ID."""
    client = _get_client(request)
    try:
        await client.remove(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None
    return MessageResponse(message=f"User {user_id} deleted")


@router.get("", response_model=list[UserResponse])
async def list_users(request: Request):
    """List all users via scan."""
    client = _get_client(request)
    records = await client.scan(NS, SET)

    users = []
    for key, meta, bins in records:
        if key and meta and bins:
            user_id = key[2]  # primary key
            users.append(_to_response(str(user_id), meta, bins))
    return users
