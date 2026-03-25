from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

import aerospike_py
from aerospike_py import AsyncClient
from aerospike_py.exception import RecordNotFound
from app.config import settings
from app.dependencies import get_client
from app.models import MessageResponse, UserCreate, UserResponse, UserUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

NS = settings.aerospike_namespace
SET = settings.aerospike_set


def _key(user_id: str) -> tuple[str, str, str]:
    return (NS, SET, user_id)


def _to_response(user_id: str, meta, bins: dict | None) -> UserResponse:
    if bins is None:
        raise HTTPException(status_code=500, detail="Record exists but has no bin data")
    if meta is None:
        logger.warning("Unexpected None meta for record %s", user_id)
    return UserResponse(
        user_id=user_id,
        name=bins["name"],
        email=bins["email"],
        age=bins["age"],
        generation=meta.gen if meta is not None else 0,
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, client: AsyncClient = Depends(get_client)):
    """Create a new user."""
    user_id = uuid.uuid4().hex
    key = _key(user_id)

    bins = {"user_id": user_id, **body.model_dump()}
    await client.put(key, bins)

    record = await client.get(key)
    return _to_response(user_id, record.meta, record.bins)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, client: AsyncClient = Depends(get_client)):
    """Get a user by ID."""
    try:
        record = await client.get(_key(user_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None
    return _to_response(user_id, record.meta, record.bins)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, body: UserUpdate, client: AsyncClient = Depends(get_client)):
    """Update an existing user (partial update)."""
    key = _key(user_id)

    update_bins = body.model_dump(exclude_none=True)
    if not update_bins:
        raise HTTPException(status_code=422, detail="No fields to update")

    # Use UPDATE_ONLY policy to atomically fail if the record doesn't exist
    # (prevents TOCTOU race — no separate existence check needed).
    try:
        await client.put(key, update_bins, policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY})
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="User not found") from None

    # Re-read to return the updated record. If the record is deleted between
    # put and get by another request, the global exception handler maps
    # RecordNotFound → 404, which is acceptable.
    record = await client.get(key)
    return _to_response(user_id, record.meta, record.bins)


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
    for record in records:
        if record.bins is None:
            continue
        # query() returns user_key=None due to aerospike-core alpha limitation,
        # so prefer the user_id stored in bins at creation time.
        user_id = record.bins.get("user_id") or (record.key.user_key if record.key else None)
        if user_id is None or not isinstance(record.bins.get("name"), str):
            continue
        result.append(_to_response(str(user_id), record.meta, record.bins))
    return result
