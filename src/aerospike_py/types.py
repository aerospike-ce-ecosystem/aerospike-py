"""Typed data structures for aerospike-py API inputs and outputs."""

from typing import Any, NamedTuple, TypedDict

# ---------------------------------------------------------------------------
# NamedTuple types (return values - runtime wrapping)
# ---------------------------------------------------------------------------


class AerospikeKey(NamedTuple):
    """Aerospike record key."""

    namespace: str
    set_name: str
    user_key: str | int | bytes | None
    digest: bytes


class RecordMetadata(NamedTuple):
    """Record metadata."""

    gen: int
    ttl: int


Bins = dict[str, Any]


class Record(NamedTuple):
    """Full record: (key, meta, bins)."""

    key: AerospikeKey | None
    meta: RecordMetadata | None
    bins: Bins | None


class ExistsResult(NamedTuple):
    """Exists check result: (key, meta)."""

    key: AerospikeKey | None
    meta: RecordMetadata | None


class InfoNodeResult(NamedTuple):
    """Info command result per node."""

    node_name: str
    error_code: int
    response: str


class BinTuple(NamedTuple):
    """Single bin name-value pair (for operate_ordered)."""

    name: str
    value: Any


class OperateOrderedResult(NamedTuple):
    """operate_ordered result."""

    key: AerospikeKey | None
    meta: RecordMetadata | None
    ordered_bins: list[BinTuple]


# ---------------------------------------------------------------------------
# TypedDict types (input parameters - annotation only)
# ---------------------------------------------------------------------------


class ReadPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    sleep_between_retries: int
    filter_expression: Any
    expressions: Any
    replica: int
    read_mode_ap: int


class WritePolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    durable_delete: bool
    key: int
    exists: int
    gen: int
    commit_level: int
    ttl: int
    filter_expression: Any
    expressions: Any


class BatchPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    filter_expression: Any


class AdminPolicy(TypedDict, total=False):
    timeout: int


class QueryPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    max_records: int
    records_per_second: int
    filter_expression: Any
    expressions: Any


class WriteMeta(TypedDict, total=False):
    gen: int
    ttl: int


class ClientConfig(TypedDict, total=False):
    hosts: list[tuple[str, int]]
    cluster_name: str
    auth_mode: int
    user: str
    password: str
    timeout: int
    idle_timeout: int
    max_conns_per_node: int
    min_conns_per_node: int
    tend_interval: int
    use_services_alternate: bool


class Privilege(TypedDict, total=False):
    code: int
    ns: str
    set: str


class UserInfo(TypedDict):
    user: str
    roles: list[str]
    conns_in_use: int


class RoleInfo(TypedDict):
    name: str
    privileges: list[Privilege]
    allowlist: list[str]
    read_quota: int
    write_quota: int
