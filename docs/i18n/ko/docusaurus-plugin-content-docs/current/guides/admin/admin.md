---
title: 사용자 및 역할 관리 가이드
sidebar_label: 사용자 및 역할 관리
sidebar_position: 1
slug: /guides/admin
description: 보안이 활성화된 Aerospike 클러스터의 사용자 및 역할 관리
---

이 기능을 사용하려면 security가 활성화된 Aerospike server가 필요합니다.

## User Management

```python
import aerospike_py as aerospike

# user 생성
client.admin_create_user("alice", "secure_password", ["read-write"])

# 비밀번호 변경
client.admin_change_password("alice", "new_password")

# role grant / revoke
client.admin_grant_roles("alice", ["sys-admin"])
client.admin_revoke_roles("alice", ["read-write"])

# user 조회
user = client.admin_query_user_info("alice")
users = client.admin_query_users_info()

# user 삭제
client.admin_drop_user("alice")
```

## Role Management

```python
# namespace/set-scoped privilege 를 가진 role 생성
client.admin_create_role("data_reader", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"},
])

# global privilege 를 가진 role 생성
client.admin_create_role("full_admin", [
    {"code": aerospike.PRIV_SYS_ADMIN},
    {"code": aerospike.PRIV_USER_ADMIN},
])

# privilege grant / revoke
client.admin_grant_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])
client.admin_revoke_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])

# whitelist 와 quota
client.admin_set_whitelist("data_reader", ["10.0.0.0/8", "192.168.1.0/24"])
client.admin_set_quotas("data_reader", read_quota=1000, write_quota=500)

# role 조회 / 삭제
role = client.admin_query_role("data_reader")
roles = client.admin_query_roles()
client.admin_drop_role("data_reader")
```

## Privilege Code

`code`에는 int 상수 또는 asadm에서 사용하는 표준 string 이름을 지정할 수 있습니다.
이름은 대소문자를 구분하지 않으며 `_`와 `-`를 같은 문자로 처리합니다.
(`"sys_admin"` == `"sys-admin"`).

| Constant | Name | 설명 |
|----------|------|-------------|
| `PRIV_READ` | `"read"` | record 읽기 |
| `PRIV_WRITE` | `"write"` | record 쓰기 |
| `PRIV_READ_WRITE` | `"read-write"` | 읽기 + 쓰기 |
| `PRIV_READ_WRITE_UDF` | `"read-write-udf"` | 읽기, 쓰기, UDF |
| `PRIV_SYS_ADMIN` | `"sys-admin"` | system admin |
| `PRIV_USER_ADMIN` | `"user-admin"` | user 관리 |
| `PRIV_DATA_ADMIN` | `"data-admin"` | data 관리 (truncate, index) |
| `PRIV_UDF_ADMIN` | `"udf-admin"` | UDF 관리 |
| `PRIV_SINDEX_ADMIN` | `"sindex-admin"` | secondary index 관리 |
| `PRIV_TRUNCATE` | `"truncate"` | truncate operation |

## Privilege Scope

```python
{"code": aerospike.PRIV_READ}                              # Global
{"code": aerospike.PRIV_READ, "ns": "test"}                # Namespace
{"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"} # Namespace + set

# 동등한 string form — code 가 wire format (HTTP form, JSON) 으로 도착할 때 유용,
# caller 에 name → int 변환 테이블이 불필요.
{"code": "read", "ns": "test", "set": "demo"}
```
