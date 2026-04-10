# sample-fastapi

An example project using FastAPI with the `aerospike-py` AsyncClient. Exposes all major aerospike-py features (CRUD, Batch, NumPy, Query, UDF, Admin, etc.) as a REST API.

## Structure

```
sample-fastapi/
├── app/
│   ├── main.py              # FastAPI app, AsyncClient lifespan management
│   ├── config.py            # pydantic-settings based configuration
│   ├── models.py            # Pydantic request/response models
│   ├── dependencies.py      # FastAPI dependency injection (get_client)
│   └── routers/
│       ├── users.py         # User CRUD
│       ├── records.py       # Individual record operations (select, exists, touch, append, increment, etc.)
│       ├── operations.py    # Multi-operation (operate, operate_ordered)
│       ├── batch.py         # Batch read/operate/remove
│       ├── numpy_batch.py   # NumPy columnar batch read, vector similarity search
│       ├── indexes.py       # Secondary index create/drop
│       ├── truncate.py      # Set truncate
│       ├── udf.py           # UDF register/remove/apply
│       ├── admin_users.py   # Admin user management
│       ├── admin_roles.py   # Admin role management
│       └── cluster.py       # Cluster connection status/node listing
├── tests/
│   ├── conftest.py          # testcontainers-based Aerospike container fixture
│   ├── fixtures/
│   │   └── test_udf.lua     # Lua script for UDF testing
│   ├── test_health.py
│   ├── test_users.py
│   ├── test_records.py
│   ├── test_operations.py
│   ├── test_batch.py
│   ├── test_numpy_batch.py
│   ├── test_indexes.py
│   ├── test_truncate.py
│   ├── test_udf.py
│   ├── test_cluster.py
│   ├── test_admin_users.py  # skipped on CE
│   └── test_admin_roles.py  # skipped on CE
└── pyproject.toml
```

## Running

### 1. Start the Aerospike server

```bash
# from the project root
podman compose -f compose.sample-fastapi.yaml up -d
```

### 2. Install dependencies and start the server

```bash
uv sync --extra dev
uvicorn app.main:app --reload
```

The Swagger UI is available at http://localhost:8000/docs.

## Tests

Tests use `testcontainers` to automatically spin up an Aerospike container, so Docker must be running.

```bash
# from the sample-fastapi directory
uv run pytest

# from the repository root
uv run --project examples/sample-fastapi pytest
```

> Admin-related tests (16 cases) are automatically skipped because Aerospike CE does not support security features.

## API Endpoints

### Health & Cluster

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/cluster/connected` | Client connection status |
| `GET` | `/cluster/nodes` | Cluster node list |

### Users (CRUD)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/users` | Create a user |
| `GET` | `/users` | List all users |
| `GET` | `/users/{user_id}` | Get a single user |
| `PUT` | `/users/{user_id}` | Update a user (partial update) |
| `DELETE` | `/users/{user_id}` | Delete a user |

### Records (Individual Record Operations)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/records/select` | Read specific bins only |
| `POST` | `/records/exists` | Check whether a record exists |
| `POST` | `/records/touch` | Refresh TTL |
| `POST` | `/records/append` | Append to a string bin |
| `POST` | `/records/prepend` | Prepend to a string bin |
| `POST` | `/records/increment` | Increment a numeric bin |
| `POST` | `/records/remove-bin` | Remove a specific bin |

### Operations (Multiple Operations on a Single Record)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/operations/operate` | Execute multiple operations atomically |
| `POST` | `/operations/operate-ordered` | Execute operations and return results in order |

### Batch (Bulk Multi-Record Operations)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/batch/read` | Bulk read multiple records |
| `POST` | `/batch/operate` | Apply operations to multiple records in bulk |
| `POST` | `/batch/remove` | Bulk delete multiple records |

### NumPy Batch (Columnar Read & Vector Search)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/numpy-batch/read` | Columnar read using NumPy structured arrays |
| `POST` | `/numpy-batch/vector-search` | Cosine similarity vector search (top-k) |

### Index

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/indexes/integer` | Create an integer secondary index |
| `POST` | `/indexes/string` | Create a string secondary index |
| `POST` | `/indexes/geo2dsphere` | Create a geospatial index |
| `DELETE` | `/indexes/{ns}/{name}` | Drop an index |

### Truncate & UDF

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/truncate` | Set truncate |
| `POST` | `/udf/modules` | Register a UDF module |
| `DELETE` | `/udf/modules/{name}` | Remove a UDF module |
| `POST` | `/udf/apply` | Execute a UDF function |

### Admin (Enterprise Edition Only)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/users` | Create an admin user |
| `DELETE` | `/admin/users/{username}` | Delete an admin user |
| `PUT` | `/admin/users/{username}/password` | Change password |
| `POST` | `/admin/users/{username}/grant-roles` | Grant roles |
| `POST` | `/admin/users/{username}/revoke-roles` | Revoke roles |
| `GET` | `/admin/users/{username}` | Get user info |
| `GET` | `/admin/users` | List all users |
| `POST` | `/admin/roles` | Create a role |
| `DELETE` | `/admin/roles/{role}` | Delete a role |
| `POST` | `/admin/roles/{role}/grant-privileges` | Grant privileges |
| `POST` | `/admin/roles/{role}/revoke-privileges` | Revoke privileges |
| `GET` | `/admin/roles/{role}` | Get role info |
| `GET` | `/admin/roles` | List all roles |
| `PUT` | `/admin/roles/{role}/whitelist` | Set IP whitelist |
| `PUT` | `/admin/roles/{role}/quotas` | Set read/write quotas |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_AEROSPIKE_HOST` | `127.0.0.1` | Aerospike host |
| `APP_AEROSPIKE_PORT` | `3000` | Aerospike port |
| `APP_AEROSPIKE_NAMESPACE` | `test` | Namespace to use |
| `APP_AEROSPIKE_SET` | `users` | Set name to use |

## Usage Examples

```bash
# Create a user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'

# List all users
curl http://localhost:8000/users

# Batch read
curl -X POST http://localhost:8000/batch/read \
  -H "Content-Type: application/json" \
  -d '{"keys": [
    {"namespace": "test", "set_name": "users", "key": "user1"},
    {"namespace": "test", "set_name": "users", "key": "user2"}
  ]}'

# Operate (increment + read)
curl -X POST http://localhost:8000/operations/operate \
  -H "Content-Type: application/json" \
  -d '{"key": {"namespace": "test", "set_name": "users", "key": "user1"},
       "ops": [{"op": 2, "bin": "age", "val": 1}, {"op": 1, "bin": "age"}]}'

# List cluster nodes
curl http://localhost:8000/cluster/nodes
```
