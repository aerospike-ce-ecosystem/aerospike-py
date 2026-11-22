---
title: 버전별 호환성 변경
slug: /guides/version-compatibility
toc_max_heading_level: 2
description: aerospike-py 버전을 올릴 때 확인할 API와 데이터 형식 변경.
---

## 0.14.x → 0.15 {#v0-15}

0.15 후보판의 최소 Aerospike 서버 버전은 **6.4**입니다. 기존 동기·비동기 클라이언트 메서드 중 호출 인자가 바뀐 것은 `batch_write_numpy()`입니다. 네 번째 인자 `_dtype`를 생략하면 `data.dtype`를 사용하고, 다른 dtype을 명시하면 쓰기 전에 `ValueError`가 발생합니다.

### NumPy 벡터 배포 순서 {#one-element-vectors-are-stored-as-a-blob}

**shape이 `(1,)`인 필드는 읽는 클라이언트를 모두 먼저 업그레이드하세요.** 0.14.x는 이 값을 스칼라로 쓰고 0.15는 BLOB으로 씁니다. 0.15는 두 형식을 모두 읽지만, 0.14.x의 `to_numpy()`는 새 BLOB을 읽으면 `TypeError`를 냅니다.

### 반환값과 오류 처리 {#checklist}

| 사용하는 API | 0.15에서 확인할 점 |
|---|---|
| `BatchRecord` | 다섯 번째 필드 `error_type`이 추가됐습니다. 네 변수에 나눠 받던 코드는 `row.result`, `row.in_doubt`처럼 필드명으로 읽으세요. |
| 배치 쓰기 | 기본 `max_retries`가 2에서 0으로 바뀝니다. 예외에 `partial_result`가 있으면 행별 결과와 `in_doubt`를 확인한 뒤 재시도하세요. |
| `batch_read()` | `len(handle)`은 결과 매핑의 고유 키 수입니다. 중복 요청을 포함한 성공 행 수는 `handle.found_count()`로 확인하세요. |
| 필터 조건 | 잘못된 `filter_expression`은 `InvalidArgError`를 일으킵니다. 필터는 `aerospike_py.exp`로 만드세요. |
| `AsyncQuery.foreach()` | `async def` 콜백을 넘기면 `TypeError`가 발생합니다. 레코드마다 `await`하려면 `async for`를 사용하세요. |
| 예외 처리 | `apply()`의 UDF 실패는 `UDFError`, 존재하지 않는 네임스페이스 오류는 `InvalidArgError`로 처리하세요. |

### `operate_ordered()`의 중복과 순서 {#operate_ordered-returns-one-entry-per-operation}

0.14.x는 같은 bin의 응답을 묶었습니다. 0.15는 응답한 연산마다 요청 순서대로 항목을 반환하므로, 값이 3인 `x`를 두 번 읽으면 `[("x", 3), ("x", 3)]`가 됩니다. 예를 들어 쓰기와 map 연산을 한 요청에 넣으면 값을 반환하지 않는 쓰기도 `("x", None)`으로 나타납니다.

### 동시 배치 읽기의 메모리 {#memory-under-concurrent-batch-load}

720키 배치 읽기 8개를 동시에 실행한 실험에서 최대 RSS는 0.14.4의 **66–70 MiB**에서 0.15의 **75–77 MiB**로 늘었습니다. 메모리 한도가 있는 서비스는 실제 배치 크기와 동시 호출 수에서 확인하세요. [0.15 벤치마크](../performance/overview.mdx)

## 0.13.0 → 0.14.0 {#v0-14}

- `list_sort`에 알 수 없는 정렬 플래그를 넘기면 기본 정렬 대신 `ValueError`가 발생합니다. 기본 정렬에는 `LIST_SORT_DEFAULT`(0), 중복 제거에는 `LIST_SORT_DROP_DUPLICATES`(2)를 사용하세요.
- 예외의 `result_code`로 서버 오류를 구분할 수 있습니다. 없는 레코드를 `remove()`하면 `RecordNotFound`의 `result_code`는 2입니다. [0.14.0 릴리스 노트](https://github.com/aerospike-ce-ecosystem/aerospike-py/releases/tag/v0.14.0)
