---
title: Admin Guide
sidebar_label: User & Role Management
sidebar_position: 1
slug: /guides/admin
description: User and role management operations for security-enabled Aerospike clusters.
---

Admin operations require a security-enabled Aerospike server.

## User Management

### Create a User

```python
client.admin_create_user("alice", "secure_password", ["read-write"])
```

### Change Password

```python
client.admin_change_password("alice", "new_password")
```

### Grant / Revoke Roles

```python
client.admin_grant_roles("alice", ["sys-admin"])
client.admin_revoke_roles("alice", ["read-write"])
```

### Query Users

```python
# Single user
user = client.admin_query_user("alice")
print(user)  # {"user": "alice", "roles": ["sys-admin"]}

# All users
users = client.admin_query_users()
for u in users:
    print(f"{u['user']}: {u['roles']}")
```

### Drop a User

```python
client.admin_drop_user("alice")
```

## Role Management

### Create a Role

```python
import aerospike_py as aerospike

# Role with specific namespace/set privileges
client.admin_create_role("data_reader", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"},
])

# Role with global privileges
client.admin_create_role("full_admin", [
    {"code": aerospike.PRIV_SYS_ADMIN},
    {"code": aerospike.PRIV_USER_ADMIN},
])
```

### Grant / Revoke Privileges

```python
client.admin_grant_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])

client.admin_revoke_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])
```

### Set IP Whitelist

```python
client.admin_set_whitelist("data_reader", ["10.0.0.0/8", "192.168.1.0/24"])
```

### Set Quotas

```python
client.admin_set_quotas("data_reader", read_quota=1000, write_quota=500)
```

### Query Roles

```python
# Single role
role = client.admin_query_role("data_reader")
print(role)

# All roles
roles = client.admin_query_roles()
for r in roles:
    print(f"{r['role']}: {r['privileges']}")
```

### Drop a Role

```python
client.admin_drop_role("data_reader")
```

## Privilege Codes

| Constant | Description |
|----------|-------------|
| `PRIV_READ` | Read records |
| `PRIV_WRITE` | Write records |
| `PRIV_READ_WRITE` | Read and write |
| `PRIV_READ_WRITE_UDF` | Read, write, and UDF |
| `PRIV_SYS_ADMIN` | System admin (config, logs) |
| `PRIV_USER_ADMIN` | User management |
| `PRIV_DATA_ADMIN` | Data management (truncate, index) |
| `PRIV_UDF_ADMIN` | UDF management |
| `PRIV_SINDEX_ADMIN` | Secondary index management |
| `PRIV_TRUNCATE` | Truncate operations |

## Privilege Dictionary Format

```python
# Global privilege
{"code": aerospike.PRIV_READ}

# Namespace-scoped
{"code": aerospike.PRIV_READ, "ns": "test"}

# Namespace + set scoped
{"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
```
