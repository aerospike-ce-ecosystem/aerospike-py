# Constants

모든 상수는 `aerospike` 모듈에서 직접 사용할 수 있습니다.

```python
import aerospike_py as aerospike
print(aerospike.POLICY_KEY_SEND)
```

## Policy Key

키를 서버에 저장할지 여부를 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_KEY_DIGEST` | 0 | 다이제스트만 저장 (기본값) |
| `POLICY_KEY_SEND` | 1 | 키를 전송하고 저장 |

## Policy Exists

레코드가 이미 존재할 때의 동작을 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_EXISTS_IGNORE` | 0 | 무조건 쓰기 (기본값) |
| `POLICY_EXISTS_UPDATE` | 1 | 기존 레코드 업데이트 |
| `POLICY_EXISTS_UPDATE_ONLY` | 2 | 레코드가 존재하지 않으면 실패 |
| `POLICY_EXISTS_REPLACE` | 3 | 모든 빈 교체 |
| `POLICY_EXISTS_REPLACE_ONLY` | 4 | 존재하는 경우에만 교체 |
| `POLICY_EXISTS_CREATE_ONLY` | 5 | 레코드가 이미 존재하면 실패 |

## Policy Generation

세대 기반 충돌 해결을 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_GEN_IGNORE` | 0 | 세대 무시 (기본값) |
| `POLICY_GEN_EQ` | 1 | 세대가 일치할 때만 쓰기 |
| `POLICY_GEN_GT` | 2 | 세대가 더 클 때만 쓰기 |

## Policy Replica

읽기에 사용할 레플리카를 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_REPLICA_MASTER` | 0 | 마스터에서 읽기 |
| `POLICY_REPLICA_SEQUENCE` | 1 | 레플리카 간 라운드 로빈 |
| `POLICY_REPLICA_PREFER_RACK` | 2 | 랙-로컬 레플리카 우선 |

## Policy Commit Level

쓰기 커밋 보장 수준을 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_COMMIT_LEVEL_ALL` | 0 | 모든 레플리카 대기 |
| `POLICY_COMMIT_LEVEL_MASTER` | 1 | 마스터만 대기 |

## Policy Read Mode AP

AP 모드에서 읽기 일관성을 제어합니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `POLICY_READ_MODE_AP_ONE` | 0 | 하나의 노드에서 읽기 |
| `POLICY_READ_MODE_AP_ALL` | 1 | 모든 노드에서 읽기 |

## TTL Constants

| Constant | Value | 설명 |
|----------|-------|-------------|
| `TTL_NAMESPACE_DEFAULT` | 0 | 네임스페이스 기본 TTL 사용 |
| `TTL_NEVER_EXPIRE` | -1 | 만료하지 않음 |
| `TTL_DONT_UPDATE` | -2 | 쓰기 시 TTL 업데이트 안 함 |
| `TTL_CLIENT_DEFAULT` | -3 | 클라이언트 기본 TTL 사용 |

## Authentication Modes

| Constant | Value | 설명 |
|----------|-------|-------------|
| `AUTH_INTERNAL` | 0 | 내부 인증 |
| `AUTH_EXTERNAL` | 1 | 외부 (LDAP) 인증 |
| `AUTH_PKI` | 2 | PKI 인증 |

## Operators

`operate()` 및 `batch_operate()`에서 사용됩니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `OPERATOR_READ` | 1 | 빈 읽기 |
| `OPERATOR_WRITE` | 2 | 빈 쓰기 |
| `OPERATOR_INCR` | 5 | 정수/실수 빈 증가 |
| `OPERATOR_APPEND` | 9 | 문자열 빈에 추가 |
| `OPERATOR_PREPEND` | 10 | 문자열 빈 앞에 삽입 |
| `OPERATOR_TOUCH` | 11 | 레코드 TTL 리셋 |
| `OPERATOR_DELETE` | 14 | 레코드 삭제 |

## Index Types

Secondary Index 데이터 타입입니다.

| Constant | Value | 설명 |
|----------|-------|-------------|
| `INDEX_NUMERIC` | 0 | 숫자 인덱스 |
| `INDEX_STRING` | 1 | 문자열 인덱스 |
| `INDEX_BLOB` | 2 | Blob 인덱스 |
| `INDEX_GEO2DSPHERE` | 3 | 지리공간 인덱스 |

## Index Collection Types

| Constant | Value | 설명 |
|----------|-------|-------------|
| `INDEX_TYPE_DEFAULT` | 0 | 기본값 (스칼라) |
| `INDEX_TYPE_LIST` | 1 | 리스트 요소 인덱싱 |
| `INDEX_TYPE_MAPKEYS` | 2 | 맵 키 인덱싱 |
| `INDEX_TYPE_MAPVALUES` | 3 | 맵 값 인덱싱 |

## Log Levels

| Constant | Value | 설명 |
|----------|-------|-------------|
| `LOG_LEVEL_OFF` | -1 | 로깅 비활성화 |
| `LOG_LEVEL_ERROR` | 0 | 오류만 |
| `LOG_LEVEL_WARN` | 1 | 경고 이상 |
| `LOG_LEVEL_INFO` | 2 | 정보 이상 |
| `LOG_LEVEL_DEBUG` | 3 | 디버그 이상 |
| `LOG_LEVEL_TRACE` | 4 | 모든 메시지 |

## Serialization

| Constant | Value | 설명 |
|----------|-------|-------------|
| `SERIALIZER_NONE` | 0 | 직렬화 없음 |
| `SERIALIZER_PYTHON` | 1 | Python pickle |
| `SERIALIZER_USER` | 2 | 사용자 정의 직렬화 |

## List Return Types

| Constant | 설명 |
|----------|-------------|
| `LIST_RETURN_NONE` | 반환 없음 |
| `LIST_RETURN_INDEX` | 인덱스 반환 |
| `LIST_RETURN_REVERSE_INDEX` | 역순 인덱스 반환 |
| `LIST_RETURN_RANK` | 순위 반환 |
| `LIST_RETURN_REVERSE_RANK` | 역순 순위 반환 |
| `LIST_RETURN_COUNT` | 개수 반환 |
| `LIST_RETURN_VALUE` | 값 반환 |
| `LIST_RETURN_EXISTS` | 존재 여부 불리언 반환 |

## List Order

| Constant | 설명 |
|----------|-------------|
| `LIST_UNORDERED` | 정렬되지 않은 리스트 |
| `LIST_ORDERED` | 정렬된 리스트 |

## List Sort Flags

| Constant | 설명 |
|----------|-------------|
| `LIST_SORT_DEFAULT` | 기본 정렬 |
| `LIST_SORT_DROP_DUPLICATES` | 정렬 시 중복 제거 |

## List Write Flags

| Constant | 설명 |
|----------|-------------|
| `LIST_WRITE_DEFAULT` | 기본 쓰기 |
| `LIST_WRITE_ADD_UNIQUE` | 고유한 값만 추가 |
| `LIST_WRITE_INSERT_BOUNDED` | 리스트 경계 적용 |
| `LIST_WRITE_NO_FAIL` | 정책 위반 시 실패하지 않음 |
| `LIST_WRITE_PARTIAL` | 부분 성공 허용 |

## Map Return Types

| Constant | 설명 |
|----------|-------------|
| `MAP_RETURN_NONE` | 반환 없음 |
| `MAP_RETURN_INDEX` | 인덱스 반환 |
| `MAP_RETURN_REVERSE_INDEX` | 역순 인덱스 반환 |
| `MAP_RETURN_RANK` | 순위 반환 |
| `MAP_RETURN_REVERSE_RANK` | 역순 순위 반환 |
| `MAP_RETURN_COUNT` | 개수 반환 |
| `MAP_RETURN_KEY` | 키 반환 |
| `MAP_RETURN_VALUE` | 값 반환 |
| `MAP_RETURN_KEY_VALUE` | 키-값 쌍 반환 |
| `MAP_RETURN_EXISTS` | 존재 여부 불리언 반환 |

## Map Order

| Constant | 설명 |
|----------|-------------|
| `MAP_UNORDERED` | 정렬되지 않은 맵 |
| `MAP_KEY_ORDERED` | 키 순서 맵 |
| `MAP_KEY_VALUE_ORDERED` | 키-값 순서 맵 |

## Map Write Flags

| Constant | 설명 |
|----------|-------------|
| `MAP_WRITE_FLAGS_DEFAULT` | 기본 쓰기 |
| `MAP_WRITE_FLAGS_CREATE_ONLY` | 생성만 |
| `MAP_WRITE_FLAGS_UPDATE_ONLY` | 업데이트만 |
| `MAP_WRITE_FLAGS_NO_FAIL` | 정책 위반 시 실패하지 않음 |
| `MAP_WRITE_FLAGS_PARTIAL` | 부분 성공 허용 |
| `MAP_UPDATE` | 맵 업데이트 |
| `MAP_UPDATE_ONLY` | 기존 키만 업데이트 |
| `MAP_CREATE_ONLY` | 새 키만 생성 |

## Bit Write Flags

| Constant | 설명 |
|----------|-------------|
| `BIT_WRITE_DEFAULT` | 기본 쓰기 |
| `BIT_WRITE_CREATE_ONLY` | 생성만 |
| `BIT_WRITE_UPDATE_ONLY` | 업데이트만 |
| `BIT_WRITE_NO_FAIL` | 정책 위반 시 실패하지 않음 |
| `BIT_WRITE_PARTIAL` | 부분 성공 허용 |

## HLL Write Flags

| Constant | 설명 |
|----------|-------------|
| `HLL_WRITE_DEFAULT` | 기본 쓰기 |
| `HLL_WRITE_CREATE_ONLY` | 생성만 |
| `HLL_WRITE_UPDATE_ONLY` | 업데이트만 |
| `HLL_WRITE_NO_FAIL` | 정책 위반 시 실패하지 않음 |
| `HLL_WRITE_ALLOW_FOLD` | 폴드 허용 |

## Privilege Codes

| Constant | 설명 |
|----------|-------------|
| `PRIV_READ` | 읽기 권한 |
| `PRIV_WRITE` | 쓰기 권한 |
| `PRIV_READ_WRITE` | 읽기-쓰기 권한 |
| `PRIV_READ_WRITE_UDF` | 읽기-쓰기-UDF 권한 |
| `PRIV_SYS_ADMIN` | 시스템 관리자 |
| `PRIV_USER_ADMIN` | 사용자 관리자 |
| `PRIV_DATA_ADMIN` | 데이터 관리자 |
| `PRIV_UDF_ADMIN` | UDF 관리자 |
| `PRIV_SINDEX_ADMIN` | Secondary Index 관리자 |
| `PRIV_TRUNCATE` | Truncate 권한 |

## Status Codes

오류 식별을 위한 상태 코드입니다.

| Constant | 설명 |
|----------|-------------|
| `AEROSPIKE_OK` | 작업 성공 |
| `AEROSPIKE_ERR_SERVER` | 일반 서버 오류 |
| `AEROSPIKE_ERR_RECORD_NOT_FOUND` | 레코드를 찾을 수 없음 |
| `AEROSPIKE_ERR_RECORD_GENERATION` | 세대 불일치 |
| `AEROSPIKE_ERR_PARAM` | 잘못된 파라미터 |
| `AEROSPIKE_ERR_RECORD_EXISTS` | 레코드가 이미 존재함 |
| `AEROSPIKE_ERR_BIN_EXISTS` | 빈이 이미 존재함 |
| `AEROSPIKE_ERR_CLUSTER_KEY_MISMATCH` | 클러스터 키 불일치 |
| `AEROSPIKE_ERR_SERVER_MEM` | 서버 메모리 부족 |
| `AEROSPIKE_ERR_TIMEOUT` | 작업 시간 초과 |
| `AEROSPIKE_ERR_ALWAYS_FORBIDDEN` | 항상 금지됨 |
| `AEROSPIKE_ERR_PARTITION_UNAVAILABLE` | 파티션 사용 불가 |
| `AEROSPIKE_ERR_BIN_TYPE` | 빈 타입 불일치 |
| `AEROSPIKE_ERR_RECORD_TOO_BIG` | 레코드가 너무 큼 |
| `AEROSPIKE_ERR_KEY_BUSY` | 키 사용 중 |
| `AEROSPIKE_ERR_SCAN_ABORT` | 스캔 중단됨 |
| `AEROSPIKE_ERR_UNSUPPORTED_FEATURE` | 지원하지 않는 기능 |
| `AEROSPIKE_ERR_BIN_NOT_FOUND` | 빈을 찾을 수 없음 |
| `AEROSPIKE_ERR_DEVICE_OVERLOAD` | 디바이스 과부하 |
| `AEROSPIKE_ERR_KEY_MISMATCH` | 키 불일치 |
| `AEROSPIKE_ERR_INVALID_NAMESPACE` | 잘못된 네임스페이스 |
| `AEROSPIKE_ERR_BIN_NAME` | 잘못된 빈 이름 |
| `AEROSPIKE_ERR_FAIL_FORBIDDEN` | 작업 금지됨 |
| `AEROSPIKE_ERR_ELEMENT_NOT_FOUND` | 요소를 찾을 수 없음 |
| `AEROSPIKE_ERR_ELEMENT_EXISTS` | 요소가 존재함 |
| `AEROSPIKE_ERR_ENTERPRISE_ONLY` | Enterprise 전용 기능 |
| `AEROSPIKE_ERR_OP_NOT_APPLICABLE` | 적용 불가능한 작업 |
| `AEROSPIKE_ERR_FILTERED_OUT` | 레코드가 필터링됨 |
| `AEROSPIKE_ERR_LOST_CONFLICT` | 충돌 패배 |
| `AEROSPIKE_QUERY_END` | 쿼리 종료 |
| `AEROSPIKE_SECURITY_NOT_SUPPORTED` | 보안 미지원 |
| `AEROSPIKE_SECURITY_NOT_ENABLED` | 보안 비활성화 |
| `AEROSPIKE_ERR_INVALID_USER` | 잘못된 사용자 |
| `AEROSPIKE_ERR_NOT_AUTHENTICATED` | 인증되지 않음 |
| `AEROSPIKE_ERR_ROLE_VIOLATION` | 역할 위반 |
| `AEROSPIKE_ERR_UDF` | UDF 오류 |
| `AEROSPIKE_ERR_BATCH_DISABLED` | 배치 비활성화 |
| `AEROSPIKE_ERR_INDEX_FOUND` | 인덱스가 이미 존재함 |
| `AEROSPIKE_ERR_INDEX_NOT_FOUND` | 인덱스를 찾을 수 없음 |
| `AEROSPIKE_ERR_QUERY_ABORTED` | 쿼리 중단됨 |
| `AEROSPIKE_ERR_CLIENT` | 클라이언트 오류 |
| `AEROSPIKE_ERR_CONNECTION` | 연결 오류 |
| `AEROSPIKE_ERR_CLUSTER` | 클러스터 오류 |
| `AEROSPIKE_ERR_INVALID_HOST` | 잘못된 호스트 |
| `AEROSPIKE_ERR_NO_MORE_CONNECTIONS` | 더 이상 연결 불가 |
