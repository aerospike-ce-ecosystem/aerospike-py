"""Typed data structures for aerospike-py API inputs and outputs."""

from typing import Any, NamedTuple, TypeAlias, TypedDict

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


class BatchRecord(NamedTuple):
    """Single record result from a batch write/operate/remove operation."""

    key: AerospikeKey | None
    result: int
    record: Record | None
    in_doubt: bool = False


class BatchWriteResult(NamedTuple):
    """Container for batch write/operate/remove results."""

    batch_records: list[BatchRecord]


# ---------------------------------------------------------------------------
# batch_read return type aliases
# ---------------------------------------------------------------------------

UserKey: TypeAlias = str | int
"""User key type for batch_read results."""

AerospikeRecord: TypeAlias = dict[str, Any]
"""Single record bins dict: ``{bin_name: bin_value}``."""

BatchRecords: TypeAlias = dict[UserKey, AerospikeRecord]
"""batch_read return type: ``{user_key: {bin_name: bin_value}}``."""


# ---------------------------------------------------------------------------
# TypedDict types (input parameters - annotation only)
# ---------------------------------------------------------------------------


class ReadPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    sleep_between_retries: int
    filter_expression: Any
    replica: int
    read_mode_ap: int
    read_touch_ttl_percent: int


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
    read_mode_ap: int
    read_touch_ttl_percent: int


class BatchPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    filter_expression: Any
    allow_inline: bool
    allow_inline_ssd: bool
    respond_all_keys: bool
    replica: int
    read_mode_ap: int
    read_touch_ttl_percent: int
    # Batch-level write defaults — used by ``batch_write``. Per-record
    # ``WriteMeta`` entries override these fields (matching the existing
    # ``ttl``/``gen`` precedence rule).
    key: int
    exists: int
    gen: int
    commit_level: int
    durable_delete: bool
    ttl: int


class BatchReadPolicy(TypedDict, total=False):
    """Per-record batch read policy.

    Used by ``batch_read``. The transport-level options (timeouts, retries,
    ``allow_inline*``, ``respond_all_keys``) live on :class:`BatchPolicy`.
    """

    read_touch_ttl_percent: int
    filter_expression: Any


class BatchDeletePolicy(TypedDict, total=False):
    """Per-record batch delete policy.

    Used by ``batch_remove``. Transport-level options live on :class:`BatchPolicy`.
    Per-record overrides go in :class:`BatchDeleteMeta`.
    """

    gen: int  # POLICY_GEN_*
    key: int  # POLICY_KEY_DIGEST | POLICY_KEY_SEND
    commit_level: int  # POLICY_COMMIT_LEVEL_*
    durable_delete: bool
    filter_expression: Any


class BatchDeleteMeta(TypedDict, total=False):
    """Per-record meta for a single ``batch_remove`` entry.

    Mirrors :class:`WriteMeta` but for delete-relevant fields only.
    Setting ``gen`` enables CAS-style "delete only if generation matches"
    semantics — the server returns a per-record GENERATION_ERROR if the
    record's generation has advanced.
    """

    gen: int
    key: int
    commit_level: int
    durable_delete: bool


class AdminPolicy(TypedDict, total=False):
    timeout: int


class QueryPolicy(TypedDict, total=False):
    socket_timeout: int
    total_timeout: int
    max_retries: int
    max_records: int
    records_per_second: int
    filter_expression: Any
    replica: int
    read_mode_ap: int
    read_touch_ttl_percent: int
    max_concurrent_nodes: int
    record_queue_size: int
    expected_duration: int
    include_bin_data: bool
    # PartitionFilter handle returned by partition_filter_all / _by_id / _by_range
    partition_filter: Any


class WriteMeta(TypedDict, total=False):
    gen: int
    ttl: int
    key: int
    exists: int
    commit_level: int
    durable_delete: bool


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
    conn_pools_per_node: int
    tend_interval: int
    use_services_alternate: bool
    max_concurrent_operations: int
    operation_queue_timeout_ms: int


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
