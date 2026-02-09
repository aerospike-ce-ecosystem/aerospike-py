from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _sanitize_key(key: Any) -> Any:
    """Strip the digest (bytes) from an Aerospike key tuple for JSON safety."""
    if isinstance(key, (tuple, list)) and len(key) > 3:
        return list(key[:3])
    return key


# ── User models (existing) ────────────────────────────────────


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, examples=["Alice"])
    email: str = Field(..., examples=["alice@example.com"])
    age: int = Field(..., ge=0, le=200, examples=[30])


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    email: str | None = None
    age: int | None = Field(None, ge=0, le=200)


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    age: int
    generation: int = Field(description="Aerospike record generation (optimistic lock version)")


class MessageResponse(BaseModel):
    message: str


# ── Common key / metadata models ──────────────────────────────


class AerospikeKey(BaseModel):
    namespace: str = Field(..., examples=["test"])
    set_name: str = Field(..., examples=["users"])
    key: str | int = Field(..., examples=["user-001"])

    def to_tuple(self) -> tuple[str, str, str | int]:
        return (self.namespace, self.set_name, self.key)


class MetadataInput(BaseModel):
    gen: int | None = None
    ttl: int | None = None


# ── Record response models ────────────────────────────────────


class RecordResponse(BaseModel):
    key: Any = None
    meta: dict[str, Any] | None = None
    bins: dict[str, Any] | None = None

    @field_validator("key", mode="before")
    @classmethod
    def _strip_digest(cls, v: Any) -> Any:
        return _sanitize_key(v)


class ExistsResponse(BaseModel):
    key: Any = None
    meta: dict[str, Any] | None = None
    exists: bool

    @field_validator("key", mode="before")
    @classmethod
    def _strip_digest(cls, v: Any) -> Any:
        return _sanitize_key(v)


# ── Records router request models ─────────────────────────────


class SelectRequest(BaseModel):
    key: AerospikeKey
    bins: list[str] = Field(..., examples=[["name", "email"]])


class KeyRequest(BaseModel):
    key: AerospikeKey


class TouchRequest(BaseModel):
    key: AerospikeKey
    val: int = Field(0, description="TTL value in seconds")


class AppendPrependRequest(BaseModel):
    key: AerospikeKey
    bin: str = Field(..., examples=["name"])
    val: str = Field(..., examples=["_suffix"])


class IncrementRequest(BaseModel):
    key: AerospikeKey
    bin: str = Field(..., examples=["age"])
    offset: int | float = Field(..., examples=[1])


class RemoveBinRequest(BaseModel):
    key: AerospikeKey
    bin_names: list[str] = Field(..., examples=[["temp_bin"]])


# ── Operations router models ──────────────────────────────────


class OperationInput(BaseModel):
    op: int = Field(..., description="Operator constant (e.g. OPERATOR_READ)")
    bin: str = Field(..., examples=["name"])
    val: Any = None


class OperateRequest(BaseModel):
    key: AerospikeKey
    ops: list[OperationInput]
    meta: MetadataInput | None = None


class OperateOrderedResponse(BaseModel):
    meta: dict[str, Any] | None = None
    ordered_bins: list[list[Any]] = Field(description="List of [bin_name, value] pairs in operation order")


# ── Batch router models ───────────────────────────────────────


class BatchReadRequest(BaseModel):
    keys: list[AerospikeKey]
    bins: list[str] | None = None


class BatchOperateRequest(BaseModel):
    keys: list[AerospikeKey]
    ops: list[OperationInput]


class BatchRemoveRequest(BaseModel):
    keys: list[AerospikeKey]


class BatchRecordResponse(BaseModel):
    key: Any = None
    result: int | None = None
    record: RecordResponse | None = None

    @field_validator("key", mode="before")
    @classmethod
    def _strip_digest(cls, v: Any) -> Any:
        return _sanitize_key(v)


class BatchRecordsResponse(BaseModel):
    batch_records: list[BatchRecordResponse]


# ── Index router models ───────────────────────────────────────


class IndexCreateRequest(BaseModel):
    namespace: str = Field(..., examples=["test"])
    set_name: str = Field(..., examples=["users"])
    bin_name: str = Field(..., examples=["age"])
    index_name: str = Field(..., examples=["idx_users_age"])


# ── Truncate router models ────────────────────────────────────


class TruncateRequest(BaseModel):
    namespace: str = Field(..., examples=["test"])
    set_name: str = Field(..., examples=["users"])
    nanos: int = Field(0, description="Cutoff timestamp in nanoseconds (0 = truncate all)")


# ── UDF router models ─────────────────────────────────────────


class UdfPutRequest(BaseModel):
    filename: str = Field(..., examples=["example.lua"])
    udf_type: int = Field(0, description="UDF type (0 = LUA)")


class ApplyRequest(BaseModel):
    key: AerospikeKey
    module: str = Field(..., examples=["example"])
    function: str = Field(..., examples=["hello"])
    args: list[Any] | None = None


# ── Admin user models ─────────────────────────────────────────


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., examples=["newuser"])
    password: str = Field(..., examples=["secretpass"])
    roles: list[str] = Field(..., examples=[["read-write"]])


class ChangePasswordRequest(BaseModel):
    password: str = Field(..., examples=["newsecretpass"])


class RolesRequest(BaseModel):
    roles: list[str] = Field(..., examples=[["read-write", "sys-admin"]])


# ── Admin role models ─────────────────────────────────────────


class PrivilegeInput(BaseModel):
    code: int = Field(..., description="Privilege code (e.g. PRIV_READ)")
    ns: str = Field("", description="Namespace (empty = global)")
    set: str = Field("", description="Set name (empty = all sets)")


class AdminCreateRoleRequest(BaseModel):
    role: str = Field(..., examples=["custom-role"])
    privileges: list[PrivilegeInput]
    whitelist: list[str] | None = None
    read_quota: int = 0
    write_quota: int = 0


class PrivilegesRequest(BaseModel):
    privileges: list[PrivilegeInput]


class WhitelistRequest(BaseModel):
    whitelist: list[str] = Field(..., examples=[["10.0.0.0/8"]])


class QuotasRequest(BaseModel):
    read_quota: int = 0
    write_quota: int = 0


# ── Numpy batch router models ───────────────────────────────


class DtypeField(BaseModel):
    name: str = Field(..., examples=["temperature"])
    dtype: str = Field(
        ...,
        description="NumPy dtype string: 'f8' (float64), 'i4' (int32), 'S<n>' (bytes), etc.",
        examples=["f8"],
    )
    shape: list[int] | None = Field(
        None,
        description="Sub-array shape for vector fields, e.g. [768] for 768-dim embedding",
        examples=[[768]],
    )


class NumpyBatchReadRequest(BaseModel):
    keys: list[AerospikeKey]
    bins: list[str] | None = None
    dtype: list[DtypeField] = Field(
        ...,
        description="Structured array dtype specification",
        examples=[
            [
                {"name": "temperature", "dtype": "f8"},
                {"name": "humidity", "dtype": "f4"},
            ]
        ],
    )


class NumpyBatchReadResponse(BaseModel):
    columns: dict[str, list[Any]] = Field(description="Columnar data: field name → list of values")
    meta: dict[str, list[int]] = Field(description="Record metadata: gen and ttl arrays")
    result_codes: list[int]
    keys: list[str | int]
    count: int


class VectorSearchRequest(BaseModel):
    keys: list[AerospikeKey]
    query_vector: list[float] = Field(..., description="Query vector for similarity search")
    embedding_bin: str = Field("embedding", description="Bin name storing the vector blob")
    embedding_dim: int = Field(..., description="Vector dimensionality", examples=[768])
    extra_bins: list[str] | None = Field(
        None,
        description="Additional bins to return alongside similarity scores",
    )
    top_k: int = Field(10, ge=1, le=1000, description="Number of top results to return")


class VectorSearchResult(BaseModel):
    key: str | int
    score: float = Field(description="Cosine similarity score")
    bins: dict[str, Any] | None = None


class VectorSearchResponse(BaseModel):
    results: list[VectorSearchResult]
    total_found: int = Field(description="Total records successfully read")
