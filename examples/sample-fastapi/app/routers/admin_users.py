from __future__ import annotations

from typing import Any

from aerospike_py import AsyncClient
from fastapi import APIRouter, Depends

from app.dependencies import get_client
from app.models import (
    AdminCreateUserRequest,
    ChangePasswordRequest,
    MessageResponse,
    RolesRequest,
)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.post("", response_model=MessageResponse, status_code=201)
async def admin_create_user(
    body: AdminCreateUserRequest, client: AsyncClient = Depends(get_client)
):
    """Create a new admin user."""
    await client.admin_create_user(body.username, body.password, body.roles)
    return MessageResponse(message=f"User '{body.username}' created")


@router.delete("/{username}", response_model=MessageResponse)
async def admin_drop_user(username: str, client: AsyncClient = Depends(get_client)):
    """Drop an admin user."""
    await client.admin_drop_user(username)
    return MessageResponse(message=f"User '{username}' dropped")


@router.put("/{username}/password", response_model=MessageResponse)
async def admin_change_password(
    username: str,
    body: ChangePasswordRequest,
    client: AsyncClient = Depends(get_client),
):
    """Change an admin user's password."""
    await client.admin_change_password(username, body.password)
    return MessageResponse(message=f"Password changed for user '{username}'")


@router.post("/{username}/grant-roles", response_model=MessageResponse)
async def admin_grant_roles(
    username: str, body: RolesRequest, client: AsyncClient = Depends(get_client)
):
    """Grant roles to an admin user."""
    await client.admin_grant_roles(username, body.roles)
    return MessageResponse(message=f"Roles granted to user '{username}'")


@router.post("/{username}/revoke-roles", response_model=MessageResponse)
async def admin_revoke_roles(
    username: str, body: RolesRequest, client: AsyncClient = Depends(get_client)
):
    """Revoke roles from an admin user."""
    await client.admin_revoke_roles(username, body.roles)
    return MessageResponse(message=f"Roles revoked from user '{username}'")


@router.get("/{username}")
async def admin_query_user_info(
    username: str, client: AsyncClient = Depends(get_client)
) -> dict[str, Any]:
    """Query info for a specific admin user."""
    return await client.admin_query_user_info(username)


@router.get("")
async def admin_query_users_info(
    client: AsyncClient = Depends(get_client),
) -> list[dict[str, Any]]:
    """Query info for all admin users."""
    return await client.admin_query_users_info()
