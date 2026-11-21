# aerospike-py Rust 3.0·NumPy 2.x 구현 인계

**목표**는 공식 Python 클라이언트와 `operate_ordered()`의 결과를 일치시키고, NumPy 배치 읽기·쓰기와 장애 시 재시도를 바로잡는 것이다. **구현·검증은 두 차례, 정식 배포는 한 번** 진행한다. 2026-11-21 조사 기준은 `main@fe011172d`, 공개 패키지 `0.14.4`, Rust 의존성 `2.2.0`이다. 통합 브랜치는 `feat/rust-v3-numpy-integration`이다. 아래 체크박스는 모두 이번 릴리스에서 구현할 작업이고, 범위에서 뺀 항목은 [후속 작업](#후속-작업)에 따로 적는다. [이슈 #499](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/499) · [Rust 3.0 마이그레이션 가이드](https://github.com/aerospike/aerospike-client-rust/blob/v3.0.0/MIGRATION.md)

## 1차 검증 — Rust 2.2에서 결함과 호환 기준 고정

- [ ] 통합 브랜치에서 시작한다. 공식 `aerospike==18.1.0`과 두 Python 클라이언트(sync·async)에 동일한 초기 레코드·연산·정책을 적용한다. 18.1.0은 `uv.lock`의 고정값이며, 19.x로 올리는 일은 이 작업과 분리한다. 쓰기가 포함된 비교는 클라이언트마다 레코드를 초기화한다. 아래 표를 실행 가능한 비교 테스트로 남긴다.
- [ ] 1차에서는 **공식 클라이언트의 기대값만 고정한다.** Rust 2.2는 bin을 `HashMap`으로 돌려줘 순서와 중복을 복원할 수 없으므로, 바인딩 측 비교는 `xfail(strict=True)`로 둔다. 2차에서 이 xfail과 기존 skip 5개를 함께 해제한다.
- [ ] 잘못된 `exists`·`gen`은 전송 전에 거부한다. 같은 파서의 `commit_level`·`replica`·`read_mode_ap`·`expected_duration`도 알 수 없는 값을 기본값으로 바꾸지 않고 거부한다. 기존 값과 generation이 유지되는지 확인한다. `LazyBatchRecords`의 `len(handle)`은 고유 Mapping 키 수, `found_count()`는 성공 행 수, `to_list()`는 요청 순서와 슬롯 수를 보존한다. `to_dict()`는 바깥 dict의 얕은 복사임을 명시한다. [정책 파서](../rust/src/policy/mod.rs) · [배치 결과](../rust/src/batch_types.rs)
- [ ] 아래 NumPy 계약을 구현하고 현재 release wheel과 비교한다. 1차 커밋은 통합 브랜치에 별도 커밋으로 남기고, squash 병합 뒤에도 브랜치를 지우지 않는다. Rust 3.0 전환의 영향을 따로 측정하기 위해서다.

### `operate_ordered()`의 판정 기준

한 번의 원자적 서버 `operate` 요청으로 `OperateOrderedResult(key, meta, ordered_bins)`를 반환한다. 비교 대상은 `BinTuple(name, value)`의 **목록 전체**다. 공식 Python 18.1.0과 CE 8.2.0.1의 기본 정책에서 관찰한 결과는 다음과 같다. 2026-11-21에 같은 조합으로 다시 실행해 모든 행을 재현했다.

| 요청과 초기값 | 공식 클라이언트의 ordered bins |
|---|---|
| `read(c), read(a), read(c), read(b)` | `[("c", 3), ("a", 1), ("c", 3), ("b", 2)]` |
| `increment(x, 1), read(x)`, 기존 `x=2` | `[("x", 3)]` |
| `write(x, 7)` | `[]` |
| `touch(), read(b)` / `read(없는 bin), read(b)` | 두 경우 모두 `[("b", 2)]` |
| `list_append(l, 3), read(l)`, 기존 `l=[1]` | `[("l", 2), ("l", [1, 3])]` |
| `list_clear(l), read(l)`, 기존 `l=[1]` | `[("l", [])]` |
| `write(x, 7), list_size(l)`, 기존 `l=[1]` | `[("l", 1)]` |
| `write(x, 7), map_size(m)`, 원소 한 개인 map | `[("x", None), ("m", 1)]` |
| `read(없는 bin), map_size(m)` | `[("없는 bin", None), ("m", 1)]` |
| `increment(x, 1), read(x), map_size(m)`, 기존 `x=2` | `[("x", None), ("x", 3), ("m", 1)]` |
| `touch(), map_size(m)` | `[("m", 1)]` |
| `write(x, 7), bit_count(b)` / `expression_read(r)` / `hll_get_count(h)` | `write`가 `("x", None)`으로 나타난다 |

**판정 규칙.** 공식 클라이언트는 요청에 map·bit·HLL·expression 연산이 하나라도 있으면 서버에 모든 연산의 응답을 요구한다. 이때 bin 이름이 있는 연산은 값이 없어도 `(name, None)`으로 나타나고, `touch()`처럼 이름이 없는 연산은 항목을 만들지 않는다. 그런 연산이 없으면 값을 돌려준 연산만 나타난다. list 연산은 이 모드를 켜지 않는다. 18.1.0의 `operate_ordered()`는 정책 dict로 이 동작을 바꾸지 못했다.

Rust 3.0은 쓰기 연산이 하나라도 있으면 같은 응답 요구(`RESPOND_ALL_OPS`)를 항상 켠다. 그래서 요청과 `Record.results`를 단순히 `zip`하거나 모든 `Nil`을 제거하면 위 계약이 깨진다. **요청의 연산 종류로 모드를 정하고, 서버가 반환한 순서대로 이름과 값을 함께 보존한다.** 전체 bin 읽기처럼 응답 하나가 여러 결과로 확장되는 조합이 Rust 3.0.0 공개 API로 복원되지 않으면 응답 파서의 최소 upstream 변경을 검토하고, 필요하면 검증한 패치 커밋을 고정한다. 기존 `operate()`의 dict·스칼라 반환은 유지한다. sync·async는 변환기를 공유하고 기존 ordered 호환성 skip 5개를 해제한다. [호환성 테스트](../tests/compatibility/test_operate_ordered.py) · [공식 구현](https://github.com/aerospike/aerospike-client-python/blob/18.1.0/src/main/client/operate.c#L1070)

### NumPy 읽기·쓰기 계약

| 영역 | 구현과 검증 기준 |
|---|---|
| 입력 API | `batch_write_numpy(data, namespace, set_name)`에서 `data.dtype`을 사용한다. 기존 네 번째 위치 인자와 `_dtype=` 키워드를 유지한다. 명시한 dtype과 배열이 다르면 **첫 행 전송 전** `ValueError`를 낸다. |
| 레이아웃·소유권 | 양방향이 이름·offset·itemsize·byte order·`subdtype`·shape를 같은 규칙으로 검증한다. object를 포함한 중첩 dtype, 가변 길이 `StringDType`, 비네이티브 endian은 명확히 거부한다. 1차원 연속·슬라이스·역순·빈 배열을 테스트한다. 변경 가능한 Python 버퍼의 raw pointer를 비동기 작업으로 넘기지 않고, 읽기의 GIL 해제 구간을 보존한다. |
| 벡터와 수치 | `(1,)`도 벡터다. 새 쓰기는 shape에 맞는 BLOB으로 저장하고, 읽기는 종전 scalar도 길이 1 벡터로 받아들인다. 벡터 BLOB 길이 불일치는 오류로 처리한다. 고정 문자열 `S<N>`의 기존 패딩·절단 규칙은 유지한다. 유한값의 f16/f32 overflow는 `OverflowError`, 원래 NaN·±inf는 보존한다. |
| 키·행 | 출력 행 `i`는 입력 행 `i`와 대응한다. digest-only 행은 위치로 접근하며 사용자 키 인덱스에 합성 문자열·정수를 넣지 않는다. 실제 키 중복은 마지막 행을 가리킨다. 실패 행도 위치와 `result_codes`를 보존한다. Rust와 Python 경로에 동일 테스트를 적용한다. |

NumPy 2.5.5는 Python 3.12 이상이 필요하다. 패키지의 Python 3.10·3.11 지원을 유지하고, 이 환경은 설치 가능한 NumPy 2.x를 테스트한다. 우선 볼 파일은 [네이티브 변환](../rust/src/numpy_support.rs), [Python 변환](../src/aerospike_py/numpy_batch.py), [NumPy 경계값 테스트](../tests/integration/test_numpy_batch_edge_cases.py), [GIL 회귀 테스트](../tests/concurrency/test_gil_detach_to_numpy.py)다. [NumPy 2.5.5 배포 정보](https://pypi.org/project/numpy/2.5.5/)

## 2차 검증 — Rust 3.0 통합과 나머지 작업

| 작업 | 완료 기준 |
|---|---|
| [ ] 코어 이식 | `aerospike`·`aerospike-core`를 함께 올리고 lockfile을 갱신한다. key/digest, map 순서, unknown particle, CDT flag·반환 타입, query/scan을 점검한다. 기존 Python 연결·idle timeout 기본값(각 30초)을 명시적으로 유지한다. 3.0에서 바뀌는 나머지 기본값과 동작도 하나씩 유지·수용을 결정해 기록한다: `login_timeout` 5초 신설, 재시도 소진의 클라이언트 코드, 전송 후 실패한 쓰기의 `in_doubt`, `Client::new`의 클러스터 수렴 대기, 최소 서버 6.4. 위 ordered 테스트와 기존 `operate()` 예제를 최종 wheel에서 통과시킨다. |
| [ ] 배치·재시도 | in-place `batch(&mut ops)`가 전체 오류를 내도 각 행을 먼저 회수한다. 기존 예외 계층을 유지하고 부분 결과를 예외에서 읽을 수 있게 한다. 성공·없는 키(2)·필터 제외(27)·전송 실패·미응답을 구분한다. 읽기 전용 배치는 읽기 정책, 쓰기·삭제·UDF는 기본 자동 재시도 0을 쓴다. 자체 `retry=`와 내부 `max_retries`의 중복을 정리한다. 2노드 이상에서 응답이 일부 유실돼도 성공 키를 재전송하지 않고, 불확실한 증가·UDF·조건부 쓰기를 자동 재실행하지 않는지 **키·최종 값·generation·in_doubt**로 검증한다. 이를 위한 2노드 compose와 노드 정지 시나리오를 저장소에 추가한다. [실행부](../rust/src/client_ops.rs) · [#453](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/453) |
| [ ] 오류·관측성 | `Error::kind()`, 서버 코드, 원인, `in_doubt()` 분류를 Python·Prometheus·OTel이 공유한다. 서버 wire code와 클라이언트 전용 `-1` 규약을 보존한다. Rust 3.0의 클라이언트 코드는 Java 번호 체계라 공식 Python 상수와 다르므로 `result_code`로 내보내지 않는다. 연결 손실, 서버/클라이언트 timeout, 재시도 소진, 정상적인 `exists()` miss를 양쪽 클라이언트에서 구분한다. 입력 오류·노드 장애가 내부 버그로 기록되는 문제와 신고 저장소 주소를 고친다. [오류 변환](../rust/src/errors.rs) · [#445](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/445) |
| [ ] 비동기 query/scan | 취소 가능한 Rust 스트림에 `results()`·`foreach()`를 연결하고 async iterator를 추가한다. 취소가 완료된 뒤 새 콜백이 시작되지 않아야 한다. 실행 중 콜백, `False`, 콜백 예외, 느린 소비자, 조기 종료, `close()` 후 연결·메모리 회수를 검증한다. UDF·쿼리의 동시 실행 제한도 점검한다. [현재 래퍼](../src/aerospike_py/_async_client.py) · [쿼리 실행부](../rust/src/query.rs) |
| [ ] 성능·리팩터링 | 쓰기 행 파싱·중간 벡터·행 복제, 읽기 키 인덱스 생성, flat-key 입력을 각각 측정한다. ordered 변환·행 판정·dtype 검증을 공유한다. 비공개 구조체를 `transmute`하는 테스트를 교체하고 fuzz가 운영 버퍼 변환 함수를 검사하게 한다. Rust CodeQL, 타입 스텁, 한·영 FAQ 및 서버별 지원표, `project-goals` 스킬의 Rust 버전 서술을 갱신한다. [flat-key 제안 #446](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/446) · [CodeQL #454](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/454) |

## 검증 기록과 단일 릴리스

1. **기준값을 재현한다.** 이전 조사에서 2.2 바인딩은 Rust 318개, Python 단위·통합 1,477개, 공식 호환성 209개가 통과했다. 별도 NumPy 2.5.5 실행에서는 관련 테스트 101개가 통과했다. CPython 3.13.11, CE 8.2.0.1 단일 노드, release wheel, 720행 × float64 8필드, 경쟁 작업 없음, 워밍업 5회 후 51회 중앙값은 기존 핸들 `to_numpy` **0.113 ms**, 전체 읽기 **6.195 ms**, 전체 쓰기 **8.203 ms**였다. 이는 변경 전 참고치다. 이 수치를 내는 스크립트를 [`benchmark/numpy_microbench.py`](../benchmark/numpy_microbench.py)로 저장소에 두고, 경쟁 CPU 작업을 넣은 기준값도 변경 전에 함께 잰다. 경쟁 작업 없는 마이크로벤치는 GIL 점유 회귀를 놓친다.
2. **두 단계에서 동일하게 검증한다.** 서버를 준비한 뒤 `make test-rust`, `AEROSPIKE_REQUIRE_SERVER=1 make test-integration`, `AEROSPIKE_REQUIRE_SERVER=1 make test-compat`, `make test-unit`, `make test-concurrency`를 실행한다. 최종 단계에서 lint·typecheck·문서 빌드, 최소 Rust 버전, 지원 플랫폼 wheel 설치, CPython 3.13·free-threaded, 고정 서버 7.2·8.1·8.2 및 다중 노드 장애를 확인한다. CI 통합 매트릭스도 `latest` 대신 이 세 버전으로 고정한다. 로컬 `make run-aerospike-ce`는 CE 8.1.0.3을 띄우므로, 8.2 기준값과 비교할 때는 같은 이미지로 맞춘다. 기존 패키지가 쓴 레코드를 **최종 wheel**로 읽는다. 경쟁 Python 작업을 넣어 p50/p95/p99·처리량·이벤트 루프 지연·최대 RSS를 전후 비교하고 커밋, 환경, skip 사유를 기록한다. [Makefile](../Makefile) · [벤치마크](../benchmark/gil_starvation.py) · [과거 성능 회귀](../POSTMORTEM-v0.5.6-batch-regression.md)
3. **한 번 병합하고 배포한다.** 1차·2차 커밋을 같은 통합 브랜치의 `main` 대상 draft PR에서 검증한다. hot path를 건드리므로 PR을 열기 전에 `perf-impact-reviewer` 판정이나 벤치마크 결과가 있어야 한다. 없으면 `gh pr create`가 훅에서 거부된다. 중간 커밋은 통합 브랜치에 둔다. `main`에 배포 대상 변경이 들어가면 매일 한국 시간 07:00 자동 릴리스 대상이 된다. 최종 squash 제목은 `feat!:`를 사용하고, 릴리스 시점에도 최신 minor가 `0.14`이면 목표는 **`v0.15.0`**이다. 한 번의 GitHub Release 발행이 wheel·sdist의 PyPI 게시를 시작한다. [CI 트리거](../.github/workflows/ci.yaml) · [버전 계산](../.github/workflows/daily-release.yml) · [게시 조건](../.github/workflows/publish.yaml) · [PR 게이트](../.claude/hooks/pr-perf-gate.sh)
4. **사용자 마이그레이션을 한 곳에 설명한다.** 위치는 문서 사이트의 [`guides/migration-0.15.md`](docs/guides/migration-0.15.md)와 한국어 번역이다. ordered 중복 항목과 조건부 `None`, Mapping 길이, NumPy 합성 키 제거·dtype 검증·벡터 길이·overflow, 쓰기 재시도와 부분 실패에 대해 변경 전후 예제를 싣는다. 특히 `(1,)`은 **서버 저장 타입이 scalar에서 BLOB으로 바뀐다.** 같은 bin을 공유하는 모든 reader가 두 형식을 읽을 수 있게 배포한 뒤 writer를 전환한다. **writer를 전환한 뒤에는 0.14.x로 되돌릴 수 없다.** 0.14.x reader는 `(1,)` 필드의 BLOB을 `TypeError`로 거부한다.

## 후속 작업

이번 릴리스에서 구현하지 않는다. #499가 의존성 업그레이드의 선행 조건이 아닌 별도 결정으로 분류한 항목이고, #315·#318은 2026-08-17에 `NOT_PLANNED`로 닫혀 있다.

- **SC 읽기 모드 4종**(`Session`·`Linearize`·`AllowReplica`·`AllowUnavailable`)과 **다중 레코드 트랜잭션**은 Enterprise Edition의 SC namespace가 있어야 검증할 수 있다. 저장소의 compose와 CI는 CE뿐이므로 EE 테스트 환경을 먼저 마련한다. 트랜잭션은 commit·abort·commit 결과 불확실 후 복구를 검증한다. [SC #315](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/315) · [트랜잭션 #466](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/466)
- **직렬화 가능한 재개 커서**는 `PartitionFilter` 직렬화를 쓰며, 이는 현재 켜지 않은 `serialization` cargo feature 뒤에 있다. 커서 복원에 쓰는 `partitions`·`PartitionStatus`는 upstream이 지원 API가 아니라고 숨겨 둔 필드다. 중단·재시작 후 누락과 중복을 검증한다. [커서 #318](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/318)
