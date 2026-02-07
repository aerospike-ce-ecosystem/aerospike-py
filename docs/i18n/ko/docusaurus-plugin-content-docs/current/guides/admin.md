---
title: Admin Guide
sidebar_label: Admin
sidebar_position: 7
description: 보안 활성화 Aerospike 클러스터 사용자 및 역할 관리
---

관리 작업에는 보안이 활성화된 Aerospike 서버가 필요합니다.

## User Management

### Create User

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

### Query User

```python
# 단일 사용자
user = client.admin_query_user("alice")
print(user)  # {"user": "alice", "roles": ["sys-admin"]}

# 모든 사용자
users = client.admin_query_users()
for u in users:
    print(f"{u['user']}: {u['roles']}")
```

### Drop User

```python
client.admin_drop_user("alice")
```

## Role Management

### Create Role

```python
import aerospike_py as aerospike

# 특정 namespace/set 권한이 있는 역할
client.admin_create_role("data_reader", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"},
])

# 전역 권한이 있는 역할
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

### Query Role

```python
# 단일 역할
role = client.admin_query_role("data_reader")
print(role)

# 모든 역할
roles = client.admin_query_roles()
for r in roles:
    print(f"{r['role']}: {r['privileges']}")
```

### Drop Role

```python
client.admin_drop_role("data_reader")
```

## Privilege Codes

| 상수 | 설명 |
|------|------|
| `PRIV_READ` | record 읽기 |
| `PRIV_WRITE` | record 쓰기 |
| `PRIV_READ_WRITE` | 읽기 및 쓰기 |
| `PRIV_READ_WRITE_UDF` | 읽기, 쓰기, 및 UDF |
| `PRIV_SYS_ADMIN` | 시스템 관리 (설정, 로그) |
| `PRIV_USER_ADMIN` | 사용자 관리 |
| `PRIV_DATA_ADMIN` | 데이터 관리 (truncate, 인덱스) |
| `PRIV_UDF_ADMIN` | UDF 관리 |
| `PRIV_SINDEX_ADMIN` | Secondary Index 관리 |
| `PRIV_TRUNCATE` | Truncate 작업 |

## Privilege Dictionary Format

```python
# 전역 권한
{"code": aerospike.PRIV_READ}

# namespace 범위
{"code": aerospike.PRIV_READ, "ns": "test"}

# namespace + set 범위
{"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
```
