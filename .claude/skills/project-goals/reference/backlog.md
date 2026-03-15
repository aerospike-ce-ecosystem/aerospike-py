# Backlog

미구현 및 개선 과제. 우선순위 미정.

## Goal 1: Rust v2 바인딩

- HyperLogLog 연산 헬퍼
- Bitwise 연산 헬퍼
- Query Pagination (파티션 필터 기반)
- Aggregate (UDF 기반 MapReduce)
- Connection pool 세부 설정 노출
- Rack-aware 읽기 최적화

## Goal 2: 성능

- sync 10% gap은 aerospike crate async-only 구조상 한계 — 수용 범위
- `batch_write_numpy` 성능 비교 벤치마크 미작성

## Goal 3: Observability

- e2e OTel tracing 통합 테스트 (in-memory exporter 사용)
- logging 전용 단위 테스트
- 운영 후 metrics histogram이 실제 ops 반영하는지 통합 테스트

## Goal 4: NumPy v2 통합

- `batch_write_numpy` 통합 테스트 (write → read roundtrip)
- f16 (float16) 통합 테스트
- sub-array dtype (embedding) 통합 테스트

## Goal 5: Type 기반 객체

- `batch_read` 결과 `BatchRecord.record` → `Record` NamedTuple 래핑
- 정책 파라미터 시그니처: `dict[str, Any]` → `Optional[ReadPolicy]` 등으로 타입 강화
- admin 반환값: `dict[str, Any]` → `UserInfo` / `RoleInfo` TypedDict 래핑
