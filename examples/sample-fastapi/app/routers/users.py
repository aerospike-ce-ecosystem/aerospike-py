from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

import aerospike_py
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


def _to_response(user_id: str, meta, bins: dict | None) -> UserResponse:
    if bins is None:
        raise HTTPException(status_code=500, detail="Record exists but has no bin data")
    return UserResponse(
        user_id=user_id,
        name=bins["name"],
        email=bins["email"],
        age=bins["age"],
        generation=meta.gen if meta is not None else 0,
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, request: Request):
    """Create a new user."""
    client = _get_client(request)
    user_id = uuid.uuid4().hex
    key = _key(user_id)

    bins = {"user_id": user_id, **body.model_dump()}
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

    update_bins = body.model_dump(exclude_none=True)
    if not update_bins:
        raise HTTPException(status_code=422, detail="No fields to update")

    # Use UPDATE_ONLY policy to atomically fail if the record was deleted
    # between our check and write (prevents TOCTOU race).
    try:
        await client.put(key, update_bins, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY})
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None

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
    """List all users by scanning the set via query().results()."""
    client = _get_client(request)
    records = await client.query(NS, SET).results()
    result = []
    for key, meta, bins in records:
        if bins is None:
            continue
        # query() returns user_key=None due to aerospike-core alpha limitation,
        # so prefer the user_id stored in bins at creation time.
        user_id = bins.get("user_id") or (key[2] if key else None)
        if user_id is None or not isinstance(bins.get("name"), str):
            continue
        result.append(_to_response(str(user_id), meta, bins))
    return result
