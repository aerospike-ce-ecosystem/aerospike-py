# aerospike-py Rust 3.0·NumPy 2.x 구현 인계

**목표**는 공식 Python 클라이언트와 `operate_ordered()`의 결과를 일치시키고, NumPy 배치 읽기·쓰기와 장애 시 재시도를 바로잡는 것이다. **구현·검증은 두 차례, 정식 배포는 한 번** 진행한다. 2026-11-21 조사 기준은 `main@fe011172d`, 공개 패키지 `0.14.4`, Rust 의존성 `2.2.0`이다. 통합 브랜치는 `feat/rust-v3-numpy-integration`이다. 아래 체크박스는 모두 이번 릴리스에서 구현할 작업이고, 범위에서 뺀 항목은 [후속 작업](#후속-작업)에 따로 적는다. **2026-11-22에 전부 구현하고 로컬 검증을 마쳤다.** 실행한 검증과 수치, 결정, 작업 중 발견한 문제는 [검증 결과](#검증-결과-2026-11-22)에 있다. [이슈 #499](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/499) · [Rust 3.0 마이그레이션 가이드](https://github.com/aerospike/aerospike-client-rust/blob/v3.0.0/MIGRATION.md)

## 1차 검증 — Rust 2.2에서 결함과 호환 기준 고정

- [x] 통합 브랜치에서 시작한다. 공식 `aerospike==18.1.0`과 두 Python 클라이언트(sync·async)에 동일한 초기 레코드·연산·정책을 적용한다. 18.1.0은 `uv.lock`의 고정값이며, 19.x로 올리는 일은 이 작업과 분리한다. 쓰기가 포함된 비교는 클라이언트마다 레코드를 초기화한다. 아래 표를 실행 가능한 비교 테스트로 남긴다.
- [x] 1차에서는 **공식 클라이언트의 기대값만 고정한다.** Rust 2.2는 bin을 `HashMap`으로 돌려줘 순서와 중복을 복원할 수 없으므로, 바인딩 측 비교는 `xfail(strict=True)`로 둔다. 2차에서 이 xfail과 기존 skip 5개를 함께 해제한다.
- [x] 잘못된 `exists`·`gen`은 전송 전에 거부한다. 같은 파서의 `commit_level`·`replica`·`read_mode_ap`·`expected_duration`도 알 수 없는 값을 기본값으로 바꾸지 않고 거부한다. 기존 값과 generation이 유지되는지 확인한다. `LazyBatchRecords`의 `len(handle)`은 고유 Mapping 키 수, `found_count()`는 성공 행 수, `to_list()`는 요청 순서와 슬롯 수를 보존한다. `to_dict()`는 바깥 dict의 얕은 복사임을 명시한다. [정책 파서](../rust/src/policy/mod.rs) · [배치 결과](../rust/src/batch_types.rs)
- [x] 아래 NumPy 계약을 구현하고 현재 release wheel과 비교한다. 1차 커밋은 통합 브랜치에 별도 커밋으로 남기고, squash 병합 뒤에도 브랜치를 지우지 않는다. Rust 3.0 전환의 영향을 따로 측정하기 위해서다.

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
| [x] 코어 이식 | `aerospike`·`aerospike-core`를 함께 올리고 lockfile을 갱신한다. key/digest, map 순서, unknown particle, CDT flag·반환 타입, query/scan을 점검한다. 기존 Python 연결·idle timeout 기본값(각 30초)을 명시적으로 유지한다. 3.0에서 바뀌는 나머지 기본값과 동작도 하나씩 유지·수용을 결정해 기록한다: `login_timeout` 5초 신설, 재시도 소진의 클라이언트 코드, 전송 후 실패한 쓰기의 `in_doubt`, `Client::new`의 클러스터 수렴 대기, 최소 서버 6.4. 위 ordered 테스트와 기존 `operate()` 예제를 최종 wheel에서 통과시킨다. |
| [x] 배치·재시도 | in-place `batch(&mut ops)`가 전체 오류를 내도 각 행을 먼저 회수한다. 기존 예외 계층을 유지하고 부분 결과를 예외에서 읽을 수 있게 한다. 성공·없는 키(2)·필터 제외(27)·전송 실패·미응답을 구분한다. 읽기 전용 배치는 읽기 정책, 쓰기·삭제·UDF는 기본 자동 재시도 0을 쓴다. 자체 `retry=`와 내부 `max_retries`의 중복을 정리한다. 2노드 이상에서 응답이 일부 유실돼도 성공 키를 재전송하지 않고, 불확실한 증가·UDF·조건부 쓰기를 자동 재실행하지 않는지 **키·최종 값·generation·in_doubt**로 검증한다. 이를 위한 2노드 compose와 노드 정지 시나리오를 저장소에 추가한다. [실행부](../rust/src/client_ops.rs) · [#453](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/453) |
| [x] 오류·관측성 | `Error::kind()`, 서버 코드, 원인, `in_doubt()` 분류를 Python·Prometheus·OTel이 공유한다. 서버 wire code와 클라이언트 전용 `-1` 규약을 보존한다. Rust 3.0의 클라이언트 코드는 Java 번호 체계라 공식 Python 상수와 다르므로 `result_code`로 내보내지 않는다. 연결 손실, 서버/클라이언트 timeout, 재시도 소진, 정상적인 `exists()` miss를 양쪽 클라이언트에서 구분한다. 입력 오류·노드 장애가 내부 버그로 기록되는 문제와 신고 저장소 주소를 고친다. [오류 변환](../rust/src/errors.rs) · [#445](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/445) |
| [x] 비동기 query/scan | 취소 가능한 Rust 스트림에 `results()`·`foreach()`를 연결하고 async iterator를 추가한다. 취소가 완료된 뒤 새 콜백이 시작되지 않아야 한다. 실행 중 콜백, `False`, 콜백 예외, 느린 소비자, 조기 종료, `close()` 후 연결·메모리 회수를 검증한다. UDF·쿼리의 동시 실행 제한도 점검한다. [현재 래퍼](../src/aerospike_py/_async_client.py) · [쿼리 실행부](../rust/src/query.rs) |
| [x] 성능·리팩터링 | 쓰기 행 파싱·중간 벡터·행 복제, 읽기 키 인덱스 생성, flat-key 입력을 각각 측정한다. ordered 변환·행 판정·dtype 검증을 공유한다. 비공개 구조체를 `transmute`하는 테스트를 교체하고 fuzz가 운영 버퍼 변환 함수를 검사하게 한다. Rust CodeQL, 타입 스텁, 한·영 FAQ 및 서버별 지원표, `project-goals` 스킬의 Rust 버전 서술을 갱신한다. [flat-key 제안 #446](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/446) · [CodeQL #454](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/454) |

## 검증 기록과 단일 릴리스

1. **기준값을 재현한다.** 이전 조사에서 2.2 바인딩은 Rust 318개, Python 단위·통합 1,477개, 공식 호환성 209개가 통과했다. 별도 NumPy 2.5.5 실행에서는 관련 테스트 101개가 통과했다. CPython 3.13.11, CE 8.2.0.1 단일 노드, release wheel, 720행 × float64 8필드, 경쟁 작업 없음, 워밍업 5회 후 51회 중앙값은 기존 핸들 `to_numpy` **0.113 ms**, 전체 읽기 **6.195 ms**, 전체 쓰기 **8.203 ms**였다. 이는 변경 전 참고치다. 이 수치를 내는 스크립트를 [`benchmark/numpy_microbench.py`](../benchmark/numpy_microbench.py)로 저장소에 두고, 경쟁 CPU 작업을 넣은 기준값도 변경 전에 함께 잰다. 경쟁 작업 없는 마이크로벤치는 GIL 점유 회귀를 놓친다.
2. **두 단계에서 동일하게 검증한다.** 서버를 준비한 뒤 `make test-rust`, `AEROSPIKE_REQUIRE_SERVER=1 make test-integration`, `AEROSPIKE_REQUIRE_SERVER=1 make test-compat`, `make test-unit`, `make test-concurrency`를 실행한다. 최종 단계에서 lint·typecheck·문서 빌드, 최소 Rust 버전, 지원 플랫폼 wheel 설치, CPython 3.13·free-threaded, 고정 서버 7.2·8.1·8.2 및 다중 노드 장애를 확인한다. CI 통합 매트릭스도 `latest` 대신 이 세 버전으로 고정한다. 로컬 `make run-aerospike-ce`는 CE 8.1.0.3을 띄우므로, 8.2 기준값과 비교할 때는 같은 이미지로 맞춘다. 기존 패키지가 쓴 레코드를 **최종 wheel**로 읽는다. 경쟁 Python 작업을 넣어 p50/p95/p99·처리량·이벤트 루프 지연·최대 RSS를 전후 비교하고 커밋, 환경, skip 사유를 기록한다. [Makefile](../Makefile) · [벤치마크](../benchmark/gil_starvation.py) · [과거 성능 회귀](../POSTMORTEM-v0.5.6-batch-regression.md)
3. **한 번 병합하고 배포한다.** 1차·2차 커밋을 같은 통합 브랜치의 `main` 대상 draft PR에서 검증한다. hot path를 건드리므로 PR을 열기 전에 `perf-impact-reviewer` 판정이나 벤치마크 결과가 있어야 한다. 없으면 `gh pr create`가 훅에서 거부된다. 중간 커밋은 통합 브랜치에 둔다. `main`에 배포 대상 변경이 들어가면 매일 한국 시간 07:00 자동 릴리스 대상이 된다. 최종 squash 제목은 `feat!:`를 사용하고, 릴리스 시점에도 최신 minor가 `0.14`이면 목표는 **`v0.15.0`**이다. 한 번의 GitHub Release 발행이 wheel·sdist의 PyPI 게시를 시작한다. [CI 트리거](../.github/workflows/ci.yaml) · [버전 계산](../.github/workflows/daily-release.yml) · [게시 조건](../.github/workflows/publish.yaml) · [PR 게이트](../.claude/hooks/pr-perf-gate.sh)
4. **사용자 마이그레이션을 한 곳에 설명한다.** 위치는 문서 사이트의 [`guides/migration-0.15.md`](docs/guides/migration-0.15.md)와 한국어 번역이다. ordered 중복 항목과 조건부 `None`, Mapping 길이, NumPy 합성 키 제거·dtype 검증·벡터 길이·overflow, 쓰기 재시도와 부분 실패에 대해 변경 전후 예제를 싣는다. 특히 `(1,)`은 **서버 저장 타입이 scalar에서 BLOB으로 바뀐다.** 같은 bin을 공유하는 모든 reader가 두 형식을 읽을 수 있게 배포한 뒤 writer를 전환한다. **writer를 전환한 뒤에는 0.14.x로 되돌릴 수 없다.** 0.14.x reader는 `(1,)` 필드의 BLOB을 `TypeError`로 거부한다.

## 검증 결과 (2026-11-22)

통합 브랜치 `feat/rust-v3-numpy-integration`에서 작업했다. 1차(Rust 2.2)는 커밋 `4be6dc9`·`f1b759a`이고, 2차(Rust 3.0)는 `ac227a9`부터다. 작업 단위마다 커밋 하나이며, 빌드가 깨지는 중간 커밋은 없다.

**환경.** Apple M4 Pro(12코어, 24 GiB), CPython 3.13.11, Rust 1.100.0. 서버는 podman VM 안의 Aerospike CE 8.2.0.1 단일 노드이고, 장애 시나리오는 CE 8.1.0.3 2노드(`make run-aerospike-multinode`)에서 돌렸다. 비교 기준은 PyPI의 `aerospike-py==0.14.4`다.

### 테스트

| 대상 | 결과 |
|---|---|
| Rust 단위 테스트 (`cargo test --features otel`) | 377개 통과 |
| clippy `-D warnings`(`otel`, `otel,fuzzing`), `cargo fmt --check`, ruff, pyright | 경고·오류 없음 |
| 최소 Rust 버전 (`cargo +1.87.0 check --features otel --all-targets`) | 통과 |
| Python 단위·통합·호환성·동시성, CE 8.2.0.1, NumPy 2.4.2 | 2,585개 통과, 13개 skip |
| 같은 스위트를 최종 커밋의 release wheel과 NumPy 2.5.5로 실행 | 2,572개 통과, 14개 skip. FastAPI를 설치하지 않은 환경이라 `test_fastapi_metrics.py`의 13개가 모듈째 빠졌다 |
| 통합·호환성·동시성, CE 8.1.0.3 | 1,457개 통과, 13개 skip |
| 통합·호환성·동시성, CE 7.2.0.6 | 1,456개 통과, 14개 skip |
| 서버를 재시작하는 테스트 (`-m destructive`, 단일 노드) | 4개 통과 |
| 2노드 장애 시나리오 (`make test-multinode`) | 8개 통과. 단정을 고친 뒤 12코어를 모두 점유시킨 상태로 5회 연속, 최종 코드로 평상시 2회 통과 |
| free-threaded CPython 3.14t (`tox -e py314t,freethreading-py314t`) | 단위 테스트 통과, free-threading 60개 통과 |
| fuzz 대상 3개, 각 60초 | 대상마다 약 52만 회 실행, 발견 없음. `i8` 범위 검사를 일부러 지우면 몇 초 안에 잡아낸다 |
| 문서 빌드 (`make docs-build`) | 영어·한국어 모두 성공, 깨진 링크·앵커 없음 |

skip 사유는 보안 기능 미활성(CE) 9개, truncate 직후 읽기가 비결정적인 테스트 3개, GIL이 켜진 빌드 1개이고, 7.2에서는 서버 8 이상이 필요한 `read_touch_ttl_percent` 1개가 더해진다. 8.1과 7.2의 전체 실행은 마지막 런타임 변경(`90ecbb1`, UDF 실패의 `in_doubt`) 이전 커밋에서 했다. 그 변경이 닿는 `test_error_attributes.py`는 7.2에서 다시 돌려 31개가 통과했고, 8.1 전체 실행은 반복하지 않았다.

**0.14.4와의 데이터 호환.** 0.14.4가 쓴 레코드와 브랜치가 쓴 레코드를 두 빌드가 서로 읽어 같은 값을 얻었다. 대상은 스칼라, 정수·bytes 키, TTL, CDT, `batch_write`, `(4,)` float32 벡터를 포함한 NumPy 행, `to_numpy`의 bytes, scan이다. 예외는 마이그레이션 가이드에 적은 `(1,)` 벡터 하나다. 언어별 blob(particle type 7~12) 여섯 종은 브랜치에서 모두 `bytes`로 읽히고, 0.14.4에서는 `RustPanicError`가 난다.

### 성능 (0.14.4 → 브랜치)

같은 기계, 같은 서버, NumPy 2.5.5, release wheel로 쟀다. 성능 측정용 wheel은 `8de0586`에서 빌드했고, 그 뒤의 런타임 변경은 실패 경로만 건드린 `90ecbb1` 하나다.

| `benchmark/numpy_microbench.py` (720행 × float64 8필드, 중앙값, ms) | 0.14.4 | 브랜치 |
|---|---|---|
| `to_numpy` | 0.107 | 0.096 |
| 전체 읽기 | 5.576 | 5.561 |
| 전체 쓰기 | 8.251 | 8.030 |
| 경쟁 CPU 작업이 있을 때 `to_numpy` | 7.229 | 6.837 |
| 경쟁 CPU 작업이 있을 때 전체 읽기 | 27.295 | 27.266 |
| 경쟁 CPU 작업이 있을 때 전체 쓰기 | 16.257 | 16.091 |

| `benchmark/gil_starvation.py --cpu-competitor` (720키 × 8 bin, 동시 8, 10초, 3회 중앙값) | 0.14.4 | 브랜치 |
|---|---|---|
| 처리량 (ops/s) | 76.5 | 78.0 |
| 지연 p50 / p95 / p99 (ms) | 99.08 / 156.78 / 170.24 | 99.73 / 145.69 / 160.12 |
| 이벤트 루프 지연 p50 / p95 / p99 / 최대 (ms) | 43.01 / 108.01 / 126.92 / 155.78 | 41.10 / 100.91 / 125.75 / 146.88 |
| 최대 RSS (MiB) | 67–68 | 78–84 |

| FastAPI 샘플 HTTP 부하 (동시 10, 배치 50, 10초 × 3회 중앙값, 0.14.4 대비) | rps | p50 | p99 |
|---|---|---|---|
| s1 읽기 전용 (20초 × 5회 재측정) | +0.1% | −0.7% | +1.4% |
| s2 dict 추론 | +12.2% | −11.1% | −6.9% |
| s3 NumPy 추론 | +2.3% | −3.7% | +3.4% |
| s4 gather | +3.5% | −5.0% | −1.9% |
| s4 단일 호출 | +7.6% | −10.2% | −12.3% |
| s5 부분 bin | +6.6% | −7.5% | 0.0% |

200이 아닌 응답은 없었다. s1의 첫 측정(10초 × 3회)은 p99가 +16.5%였는데, 길게 다시 재니 +1.4%여서 잡음으로 판단했다.

**비동기 query.** 20만 레코드 × 200 B에서 `results()`가 825 ms에서 458 ms로, `foreach()`가 434 ms에서 406 ms로 줄었다. 중간에 빠져나온 뒤 서버에 scan이 남아 있는 시간은 30초에서 약 0.3초가 됐다. 소비자가 읽기를 멈추면 서버는 20만 개 중 59,619개를 보낸 상태에서 멈춘다.

**단계별 시간** (`benchmark/numpy_stage_breakdown.py`, 720행 × float64 8필드, 51회 평균). 쓰기 8,950 µs 가운데 네트워크 왕복(`io`)이 6,470 µs이고, 행 파싱 234 µs, 연산 생성 123 µs, 정책 결합 6 µs다. 읽기 6,150 µs 가운데 `io`가 5,717 µs, 키 파싱 157 µs, `to_numpy` 146 µs(그중 키 인덱스 생성 18 µs)다. flat-key 입력(#446)이 없앨 수 있는 것은 키 파싱 157 µs, 즉 읽기의 약 2.6%가 상한이라 이번에는 측정만 하고 구현하지 않았다.

### 메모리는 늘었다

처리량과 지연은 같거나 나아졌지만 메모리는 비용이 있다. 동시 배치 부하에서 프로세스 RSS가 다음과 같이 늘었다.

| 부하 | 0.14.4 | 브랜치 |
|---|---|---|
| 720개 레코드 × 8 bin `batch_read`, 동시 8, 경쟁 CPU 작업 | 최대 67–68 MiB | 최대 78–84 MiB |
| 같은 배치, 동시 32, 192,000회(약 3분) | 134–190 MiB 사이를 오감(최대 192) | 243–246 MiB에서 멈춰 마지막 96,000회 동안 평탄(최대 253) |
| 50,000키 `batch_read` 한 번 | 키당 2.2 KiB | 키당 2.7 KiB |

두 빌드 모두 계속 늘지는 않으므로 누수가 아니라 클라이언트가 붙잡고 있는 버퍼다. 원인은 Rust 3.0에 있다. 배치 행 구조체가 약 20% 커졌고(`BatchRecord` 320 → 408 바이트 등), 연결마다 읽기 버퍼가 4 KiB에서 64 KiB가 됐으며, 큰 버퍼를 해제하지 않고 풀에 보관한다(`use_buffer_pool` 기본 켜짐, 크기 등급마다 최대 4 MiB, 약 1분 뒤 해제). 이 설정은 지금 Python에서 바꿀 수 없다. 마이그레이션 가이드에 수치와 함께 적었다.

### 결정 기록

- **Client 기본값.** `timeout`·`idle_timeout`은 30초를 명시적으로 유지한다(3.0은 1초와 0으로 낮췄다). `login_timeout` 5초를 포함한 나머지 기본값은 upstream 값을 받아들였다.
- **재시도 소진.** `result_code`는 `-1`, `error_type`은 `"MaxRetriesExceeded"`다. Java 번호 체계의 클라이언트 코드는 Python으로 내보내지 않는다.
- **`in_doubt`.** 예외, 배치 행, span 속성이 한 함수(`errors::may_have_been_applied`)를 읽는다. upstream 판정을 두 곳에서 보정한다. 서버가 `TIMEOUT`으로 답한 쓰기 행은 in doubt로 올리고, UDF 실패는 서버의 확정 응답이므로 in doubt에서 내린다.
- **동시 실행 제한.** `apply()`는 `max_concurrent_operations` 슬롯을 차지한다. query·scan 스트림은 일부러 차지하지 않는다. 레코드마다 조회를 하는 소비자가 자기 스트림이 쥔 슬롯을 기다리며 멈추기 때문이다.
- **쓰기 배치 재시도.** 쓰기·삭제·UDF 배치의 `max_retries` 기본값은 0이다. `retry=N`과 0이 아닌 `max_retries`를 함께 주면 `InvalidArgError`다.
- **CI.** 통합 매트릭스를 7.2·8.1·8.2로 고정했고, CodeQL에 Rust(build mode `none`)를 추가했다.

### 작업 중 발견한 것

- **계획에 없던 호환성 변경 세 가지.** 모두 테스트로 고정하고 가이드에 적었다. 알 수 없는 namespace는 `InvalidArgError`가 된다(단건은 `AerospikeTimeoutError`, 배치는 `ClusterError`였다). `meta.ttl`은 초 단위로 계산돼, 쓴 직후 읽으면 설정한 값이 그대로 나온다(0.14.4는 400번 중 398번이 1초 작은 값). `BatchRecord`는 다섯 번째 필드 `error_type`이 생겨 네 이름으로 풀어 쓰는 코드가 깨진다.
- **`where()` 두 번.** 커밋 메시지는 동작 변경처럼 적었지만 0.14.x도 `InvalidArgError`를 냈다. 바뀐 것은 메시지뿐이다.
- **노드 재시작.** 같은 주소에서 노드 ID가 바뀌어 재시작하면 약 1초(tend 주기 한 번) 동안 그 노드로 라우팅하지 못한다. 2.2에서는 수 ms였다.
- **Rust client 3.0의 동작 다섯 가지를 바인딩에서 보정했다.** upstream에 보고할 만하지만 **보고하지 않았다.** (1) 배치가 일찍 반환하면 자리표시 행이 남는다. (2) 서버가 `TIMEOUT`으로 답한 배치 쓰기 행을 in doubt로 표시하지 않는다. (3) 실패한 UDF 호출을 전부 in doubt로 표시한다. (4) record stream을 drop해도 노드별 reader가 멈추지 않는다. (5) `Recordset::close()`가 막혀 있는 읽기를 깨우지 못해, 속도 제한(`records_per_second`) scan은 서버의 다음 블록까지 연결을 쥔다.
- **범위 밖에서 본 것.** `batch_operate`는 레코드별 `exists`·`gen`·`commit_level`을, `batch_remove`는 `exists`를 무시한다. NumPy의 Rust 경로와 Python 경로는 일부 잘못된 값에 서로 다른 예외를 내고, Python 경로는 byte order가 뒤집힌 필드를 받아들인다. 고치지 않았다.
- **테스트 세 건을 타이밍과 무관하게 고쳤다.** 쿼리 중간 timeout 테스트, 2노드 재시도 시나리오의 단정 두 개, `meta.ttl <= ttl` 단정 18개다. 모두 클라이언트 동작이 아니라 한가한 기계의 타이밍을 가정하고 있었다.

### 로컬에서 확인하지 못한 것

- Linux(x86_64·aarch64), Windows, macOS x86_64의 wheel 설치는 CI에서만 확인할 수 있다.
- podman VM의 시계는 호스트가 CPU를 다 쓰는 동안 어긋났다가 맞춰진다. 그 사이 truncate가 미래 시각을 기록하면 이후에 쓴 레코드가 한동안 보이지 않아, 전체 실행에서 TTL·generation 테스트 150여 개가 한꺼번에 실패한다. 세 번 겪었고 매번 시계가 맞은 뒤 다시 돌리면 통과했다. 전체 실행이 대량으로 실패하면 `date -u`와 `podman exec aerospike date -u`부터 비교한다.
- 체크아웃한 `main` 작업 폴더에 이 문서가 untracked로 남아 있으면, 그 폴더에서 이 브랜치를 체크아웃할 때 충돌한다.

## 후속 작업

이번 릴리스에서 구현하지 않는다. #499가 의존성 업그레이드의 선행 조건이 아닌 별도 결정으로 분류한 항목이고, #315·#318은 2026-08-17에 `NOT_PLANNED`로 닫혀 있다.

- **SC 읽기 모드 4종**(`Session`·`Linearize`·`AllowReplica`·`AllowUnavailable`)과 **다중 레코드 트랜잭션**은 Enterprise Edition의 SC namespace가 있어야 검증할 수 있다. 저장소의 compose와 CI는 CE뿐이므로 EE 테스트 환경을 먼저 마련한다. 트랜잭션은 commit·abort·commit 결과 불확실 후 복구를 검증한다. [SC #315](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/315) · [트랜잭션 #466](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/466)
- **직렬화 가능한 재개 커서**는 `PartitionFilter` 직렬화를 쓰며, 이는 현재 켜지 않은 `serialization` cargo feature 뒤에 있다. 커서 복원에 쓰는 `partitions`·`PartitionStatus`는 upstream이 지원 API가 아니라고 숨겨 둔 필드다. 중단·재시작 후 누락과 중복을 검증한다. [커서 #318](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/318)
- **버퍼 설정 노출.** `use_buffer_pool`과 버퍼 크기 설정을 `ClientConfig`로 내보내면 [늘어난 메모리](#메모리는-늘었다)를 사용자가 조절할 수 있다.
- **배치의 레코드별 정책.** `batch_operate`의 `exists`·`gen`·`commit_level`과 `batch_remove`의 `exists`를 적용하거나, 받지 않는다고 거부한다.
- **upstream 보고.** [작업 중 발견한 것](#작업-중-발견한-것)의 Rust client 3.0 동작 다섯 가지를 보고할지 결정한다.
