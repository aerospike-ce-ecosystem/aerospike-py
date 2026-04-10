# Backlog

Unimplemented features and improvements. Priority not yet assigned.

## Goal 1: Rust v2 Bindings

- HyperLogLog operation helpers
- Bitwise operation helpers
- Query Pagination (partition filter based)
- Aggregate (UDF-based MapReduce)
- Connection pool fine-grained configuration exposure
- Rack-aware read optimization

## Goal 2: Performance

- Sync ~10% gap is a structural limitation of the aerospike crate's async-only architecture — within acceptable range
- `batch_write_numpy` performance comparison benchmark not yet written

## Goal 3: Observability

- End-to-end OTel tracing integration test (using in-memory exporter)
- Dedicated logging unit tests
- Integration test to verify metrics histograms reflect actual ops after production use

## Goal 4: NumPy v2 Integration

- `batch_write_numpy` integration test (write → read roundtrip)
- f16 (float16) integration test
- Sub-array dtype (embedding) integration test

## Goal 5: Type-based Objects

- `batch_read` result `BatchRecord.record` → wrap as `Record` NamedTuple
- Policy parameter signatures: strengthen types from `dict[str, Any]` → `Optional[ReadPolicy]`, etc.
- Admin return values: wrap `dict[str, Any]` → `UserInfo` / `RoleInfo` TypedDict
