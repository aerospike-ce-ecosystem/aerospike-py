---
title: Admin Guide
sidebar_label: User & Role Management
sidebar_position: 1
slug: /guides/admin
description: User and role management for security-enabled Aerospike clusters.
---

Requires a security-enabled Aerospike server.

## User Management

```python
import aerospike_py as aerospike

# Create user
client.admin_create_user("alice", "secure_password", ["read-write"])

# Change password
client.admin_change_password("alice", "new_password")

# Grant / revoke roles
client.admin_grant_roles("alice", ["sys-admin"])
client.admin_revoke_roles("alice", ["read-write"])

# Query users
user = client.admin_query_user_info("alice")
users = client.admin_query_users_info()

# Drop user
client.admin_drop_user("alice")
```

## Role Management

```python
# Create role with namespace/set-scoped privileges
client.admin_create_role("data_reader", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"},
])

# Create role with global privileges
client.admin_create_role("full_admin", [
    {"code": aerospike.PRIV_SYS_ADMIN},
    {"code": aerospike.PRIV_USER_ADMIN},
])

# Grant / revoke privileges
client.admin_grant_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])
client.admin_revoke_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])

# Whitelist and quotas
client.admin_set_whitelist("data_reader", ["10.0.0.0/8", "192.168.1.0/24"])
client.admin_set_quotas("data_reader", read_quota=1000, write_quota=500)

# Query / drop roles
role = client.admin_query_role("data_reader")
roles = client.admin_query_roles()
client.admin_drop_role("data_reader")
```

## Privilege Codes

`code` accepts either the int constant or the canonical string name (asadm-style).
Names are matched case-insensitively, and `_` is a synonym for `-`
(`"sys_admin"` == `"sys-admin"`).

| Constant | Name | Description |
|----------|------|-------------|
| `PRIV_READ` | `"read"` | Read records |
| `PRIV_WRITE` | `"write"` | Write records |
| `PRIV_READ_WRITE` | `"read-write"` | Read and write |
| `PRIV_READ_WRITE_UDF` | `"read-write-udf"` | Read, write, and UDF |
| `PRIV_SYS_ADMIN` | `"sys-admin"` | System admin |
| `PRIV_USER_ADMIN` | `"user-admin"` | User management |
| `PRIV_DATA_ADMIN` | `"data-admin"` | Data management (truncate, index) |
| `PRIV_UDF_ADMIN` | `"udf-admin"` | UDF management |
| `PRIV_SINDEX_ADMIN` | `"sindex-admin"` | Secondary index management |
| `PRIV_TRUNCATE` | `"truncate"` | Truncate operations |

## Privilege Scope

```python
{"code": aerospike.PRIV_READ}                              # Global
{"code": aerospike.PRIV_READ, "ns": "test"}                # Namespace
{"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"} # Namespace + set

# Equivalent string form — useful when codes arrive from a wire format
# (HTTP form, JSON) so callers don't need a name → int translation table.
{"code": "read", "ns": "test", "set": "demo"}
```
