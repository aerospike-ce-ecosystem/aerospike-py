# Goal 5: Type 기반 객체

## NamedTuple (7종) — `src/aerospike_py/types.py`

| 타입 | 용도 |
|------|------|
| `AerospikeKey` | namespace, set_name, user_key, digest |
| `RecordMetadata` | gen, ttl |
| `Record` | key, meta, bins |
| `ExistsResult` | key, meta |
| `BinTuple` | name, value (operate_ordered 용) |
| `OperateOrderedResult` | key, meta, ordered_bins |
| `InfoNodeResult` | node_name, error_code, response |

## TypedDict (13종)

`types.py`: `ReadPolicy`, `WritePolicy`, `BatchPolicy`, `AdminPolicy`, `QueryPolicy`, `WriteMeta`, `ClientConfig`, `Privilege`, `UserInfo`, `RoleInfo`
`_types.py`: `ListPolicy`, `MapPolicy`, `HLLPolicy`

## 2단계 변환 아키텍처

```
Rust → plain PyTuple/PyDict
  → Python _wrap_record() / _wrap_exists() / _wrap_operate_ordered()
      → NamedTuple 반환
```

`_client.py` / `_async_client.py` 에서 모든 read 결과에 일관 적용.

## 주요 파일

- `src/aerospike_py/types.py` — NamedTuple + TypedDict 정의
- `src/aerospike_py/__init__.pyi` — 완전한 타입 스텁
- `rust/src/types/record.rs` — Rust → Python 원시 변환
- `rust/src/record_helpers.rs` — 지연 변환 패턴
