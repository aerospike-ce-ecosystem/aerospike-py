from __future__ import annotations

from typing import Any

from aerospike_py import AsyncClient
from fastapi import APIRouter, Depends

from app.dependencies import get_client
from app.models import (
    AdminCreateRoleRequest,
    MessageResponse,
    PrivilegesRequest,
    QuotasRequest,
    WhitelistRequest,
)

router = APIRouter(prefix="/admin/roles", tags=["admin-roles"])


def _privileges_to_dicts(privileges):
    """Convert PrivilegeInput list to Aerospike privilege dicts."""
    return [{"code": p.code, "ns": p.ns, "set": p.set} for p in privileges]


@router.post("", response_model=MessageResponse, status_code=201)
async def admin_create_role(
    body: AdminCreateRoleRequest, client: AsyncClient = Depends(get_client)
):
    """Create a new admin role."""
    privs = _privileges_to_dicts(body.privileges)
    await client.admin_create_role(
        body.role,
        privs,
        whitelist=body.whitelist,
        read_quota=body.read_quota,
        write_quota=body.write_quota,
    )
    return MessageResponse(message=f"Role '{body.role}' created")


@router.delete("/{role_name}", response_model=MessageResponse)
async def admin_drop_role(role_name: str, client: AsyncClient = Depends(get_client)):
    """Drop an admin role."""
    await client.admin_drop_role(role_name)
    return MessageResponse(message=f"Role '{role_name}' dropped")


@router.post("/{role_name}/grant-privileges", response_model=MessageResponse)
async def admin_grant_privileges(
    role_name: str,
    body: PrivilegesRequest,
    client: AsyncClient = Depends(get_client),
):
    """Grant privileges to a role."""
    privs = _privileges_to_dicts(body.privileges)
    await client.admin_grant_privileges(role_name, privs)
    return MessageResponse(message=f"Privileges granted to role '{role_name}'")


@router.post("/{role_name}/revoke-privileges", response_model=MessageResponse)
async def admin_revoke_privileges(
    role_name: str,
    body: PrivilegesRequest,
    client: AsyncClient = Depends(get_client),
):
    """Revoke privileges from a role."""
    privs = _privileges_to_dicts(body.privileges)
    await client.admin_revoke_privileges(role_name, privs)
    return MessageResponse(message=f"Privileges revoked from role '{role_name}'")


@router.get("/{role_name}")
async def admin_query_role(
    role_name: str, client: AsyncClient = Depends(get_client)
) -> dict[str, Any]:
    """Query info for a specific role."""
    return await client.admin_query_role(role_name)


@router.get("")
async def admin_query_roles(
    client: AsyncClient = Depends(get_client),
) -> list[dict[str, Any]]:
    """Query info for all roles."""
    return await client.admin_query_roles()


@router.put("/{role_name}/whitelist", response_model=MessageResponse)
async def admin_set_whitelist(
    role_name: str,
    body: WhitelistRequest,
    client: AsyncClient = Depends(get_client),
):
    """Set the IP whitelist for a role."""
    await client.admin_set_whitelist(role_name, body.whitelist)
    return MessageResponse(message=f"Whitelist set for role '{role_name}'")


@router.put("/{role_name}/quotas", response_model=MessageResponse)
async def admin_set_quotas(
    role_name: str,
    body: QuotasRequest,
    client: AsyncClient = Depends(get_client),
):
    """Set read/write quotas for a role."""
    await client.admin_set_quotas(
        role_name,
        read_quota=body.read_quota,
        write_quota=body.write_quota,
    )
    return MessageResponse(message=f"Quotas set for role '{role_name}'")
