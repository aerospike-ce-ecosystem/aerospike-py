---
name: api-admin-infra
description: aerospike-py admin (user/role management), UDF, info, truncate, and observability (prometheus metrics, opentelemetry tracing, logging)
user-invocable: false
---

Aerospike Python client (Rust/PyO3). Sync/Async API. 전체 타입/상수: `src/aerospike_py/__init__.pyi`

## Admin

```python
# User 관리
client.admin_create_user("user1", "pass", ["read-write"])
client.admin_drop_user("user1")
client.admin_change_password("user1", "new_pass")
client.admin_grant_roles("user1", ["sys-admin"])
client.admin_revoke_roles("user1", ["read-write"])
client.admin_query_user_info("user1")  # -> dict (user, roles, conns_in_use)
client.admin_query_users_info()        # -> list[dict]

# Role 관리
client.admin_create_role("role1", [{"code": aerospike_py.PRIV_READ, "ns": "test", "set": ""}])
client.admin_drop_role("role1")
client.admin_grant_privileges("role1", [{"code": aerospike_py.PRIV_WRITE, "ns": "", "set": ""}])
client.admin_revoke_privileges("role1", [{"code": aerospike_py.PRIV_WRITE, "ns": "", "set": ""}])
client.admin_query_role("role1")    # -> dict (name, privileges, allowlist, read_quota, write_quota)
client.admin_query_roles()          # -> list[dict]
client.admin_set_whitelist("role1", ["10.0.0.0/8"])
client.admin_set_quotas("role1", read_quota=1000, write_quota=500)
```

### Privilege 상수

```python
PRIV_READ, PRIV_WRITE, PRIV_READ_WRITE, PRIV_READ_WRITE_UDF
PRIV_SYS_ADMIN, PRIV_USER_ADMIN, PRIV_DATA_ADMIN
PRIV_UDF_ADMIN, PRIV_SINDEX_ADMIN, PRIV_TRUNCATE
```

## UDF (Lua only)

```python
client.udf_put("my_udf.lua")
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
client.udf_remove("my_udf")
```

## Info / Truncate

```python
from aerospike_py.types import InfoNodeResult

results: list[InfoNodeResult] = client.info_all("namespaces")
for node_name, error_code, response in results:
    print(f"{node_name}: {response}")

response: str = client.info_random_node("build")
client.truncate("test", "demo")
client.truncate("test", "demo", nanos=1234567890)  # 특정 시점 이전 레코드만
```

## Observability

```python
# Prometheus Metrics
aerospike_py.start_metrics_server(port=9464)  # /metrics HTTP 엔드포인트
metrics_text: str = aerospike_py.get_metrics()  # Prometheus text format
aerospike_py.stop_metrics_server()

# OpenTelemetry Tracing (OTEL_* 환경변수로 설정)
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# OTEL_SERVICE_NAME=my-service
# OTEL_SDK_DISABLED=true (비활성화)
aerospike_py.init_tracing()
aerospike_py.shutdown_tracing()  # 프로세스 종료 전 호출

# Logging
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

### Log Level / Auth 상수

```python
# Log Level
LOG_LEVEL_OFF=-1, LOG_LEVEL_ERROR=0, LOG_LEVEL_WARN=1,
LOG_LEVEL_INFO=2, LOG_LEVEL_DEBUG=3, LOG_LEVEL_TRACE=4

# Auth
AUTH_INTERNAL = 0, AUTH_EXTERNAL = 1, AUTH_PKI = 2
```
