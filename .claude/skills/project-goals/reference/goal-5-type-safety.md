# Goal 5: Type-based Objects

## NamedTuples (7 types) — `src/aerospike_py/types.py`

| Type | Purpose |
|------|------|
| `AerospikeKey` | namespace, set_name, user_key, digest |
| `RecordMetadata` | gen, ttl |
| `Record` | key, meta, bins |
| `ExistsResult` | key, meta |
| `BinTuple` | name, value (for operate_ordered) |
| `OperateOrderedResult` | key, meta, ordered_bins |
| `InfoNodeResult` | node_name, error_code, response |

## TypedDicts (13 types)

`types.py`: `ReadPolicy`, `WritePolicy`, `BatchPolicy`, `AdminPolicy`, `QueryPolicy`, `WriteMeta`, `ClientConfig`, `Privilege`, `UserInfo`, `RoleInfo`
`_types.py`: `ListPolicy`, `MapPolicy`, `HLLPolicy`

## Two-stage Conversion Architecture

```
Rust → plain PyTuple/PyDict
  → Python _wrap_record() / _wrap_exists() / _wrap_operate_ordered()
      → NamedTuple return
```

Applied consistently to all read results in `_client.py` / `_async_client.py`.

## Key Files

- `src/aerospike_py/types.py` — NamedTuple + TypedDict definitions
- `src/aerospike_py/__init__.pyi` — complete type stubs
- `rust/src/types/record.rs` — Rust → Python raw conversion
- `rust/src/record_helpers.rs` — lazy conversion pattern
