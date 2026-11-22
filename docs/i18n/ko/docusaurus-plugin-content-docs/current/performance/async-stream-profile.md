---
title: 비동기 쿼리 스트림 프로파일
sidebar_label: 비동기 쿼리 스트림
sidebar_position: 3
slug: /performance/async-stream-profile
description: aerospike-py와 공식 SDK가 쿼리 레코드를 Python으로 넘기는 경로와 free-threaded 빌드에서 조회 시간이 달라지는 이유를 설명합니다.
---

import useBaseUrl from '@docusaurus/useBaseUrl';

하나의 `async for` 루프에서 같은 12,000행을 끝까지 읽었을 때, Python 소비자는 aerospike-py `4aabf09`에서 **48회**, 공식 `aerospike-sdk` 1.0.0과 `aerospike-native` 1.0.0에서 **12,001회** 네이티브 Future가 완료되기를 기다렸습니다. 두 클라이언트 모두 Aerospike Rust core 3.0.0을 씁니다. Python을 한 번 깨울 때 몇 행을 넘길지는 각 바인딩이 결정합니다.

| 12,000행을 모두 읽는 데 걸린 시간 | aerospike-py | 공식 SDK | 공식 SDK 시간 / aerospike-py 시간 |
|---|---:|---:|---:|
| CPython 3.14.2 | 33.75 ms | 336.53 ms | 9.97배 |
| Free-threaded CPython 3.14.2t, GIL 꺼짐 | 41.80 ms | 196.64 ms | 4.70배 |

Apple M4 Pro에서 uvloop 0.23.0을 사용하고, 같은 호스트의 Podman VM에서 CE 8.2.0.1 단일 노드를 실행했습니다. 각 행의 정수와 160바이트 문자열을 읽어 값·중복·누락을 확인했습니다. 표는 연결과 워밍업을 마친 뒤 측정한 3회 중앙값입니다. 프로파일러를 끄고 조건별로 15회씩 다시 측정한 배수는 **10.61배**와 **5.06배**였습니다. 동기 조회, 목록 수집, 배치 읽기·쓰기는 [클라이언트 비교](./client-comparison.md)에서 각 작업에 맞는 API끼리 비교합니다.

## 서버에서 Python 루프까지 {#from-the-server-to-the-python-loop}

- **aerospike-py**는 core의 `query_foreach` 콜백으로 받은 Rust 레코드를 크기가 제한된 큐에 넣습니다. Python iterator는 로컬 목록을 다 쓰면 `next_batch(256)`으로 첫 레코드를 기다립니다. 그 시점에 이미 도착한 레코드를 최대 255개 더 꺼내고, Rust가 묶음 전체의 key·metadata·bins를 Python 객체로 변환해 목록 하나로 Future를 완료합니다. 이후 `__anext__`는 목록에 남은 행을 `Record`로 감싸 바로 돌려줍니다. [Rust 큐와 묶음 읽기](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/query_stream.rs#L596-L634) · [Python 목록 변환](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/query_stream.rs#L879-L893) · [Python iterator](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/src/aerospike_py/_async_client.py#L131-L175)
- **공식 SDK**는 core의 `query`와 수신 버퍼를 갖춘 `Recordset`을 씁니다. 네이티브 `__anext__`가 호출될 때마다 Python Future와 Tokio 작업을 하나씩 만들어 **레코드 한 건**을 꺼냅니다. 이벤트 루프에서 Future를 완료하면 SDK가 레코드를 `RecordResult`로 감싸고, 소비자가 `row.record.bins`에 처음 접근할 때 Python dict를 만들어 캐시합니다. 순차 소비에서는 앞 행을 받은 다음에야 다음 행을 요청합니다. 표의 Future 횟수는 클라이언트 프로세스 안에서 일어난 완료 통지 횟수입니다. 두 core 진입점은 같은 하위 쿼리 실행기를 사용합니다. [Core의 두 쿼리 진입점](https://github.com/aerospike/aerospike-client-rust/blob/2ed9456106daa8431860aa5afa0068d074508da6/aerospike-core/src/client.rs#L1608-L1695) · [네이티브 iterator](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/filter.rs#L873-L917) · [SDK 어댑터](https://github.com/aerospike/aerospike-client-python-sdk/blob/bd159b32edbc0d7502a726842890b43659b7b72b/aerospike_sdk/record_stream.py#L195-L217) · [Bins getter](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/record.rs#L74-L87)

## 한 번에 넘기는 행 수를 바꾼 실험 {#changing-only-the-refill-size}

동일한 aerospike-py wheel에서 한 번에 꺼낼 수 있는 행 수만 바꿨습니다. 표의 시간은 5회 중앙값입니다. Future 대기 횟수는 별도 실행에서 계측했고, 스트림의 끝을 확인하는 마지막 요청까지 포함했습니다.

| 한 번에 최대 | Future 대기 횟수 | CPython 3.14.2 | CPython 3.14.2t |
|---:|---:|---:|---:|
| 1행 | 12,001회 | 446.51 ms | 563.25 ms |
| 16행 | 751회 | 62.63 ms | 76.83 ms |
| 64행 | 189회 | 41.52 ms | 48.68 ms |
| 256행 (기본값) | 48회 | 31.99 ms | 37.69 ms |

기본값에서는 256행씩 46번, 남은 224행을 한 번 받은 뒤 마지막 한 번으로 종료를 확인했습니다. 레코드가 천천히 들어올 때는 한 행만 받아도 소비를 재개할 수 있습니다. 상한을 한 행으로 줄이면 동일한 aerospike-py 바이너리가 두 빌드 모두에서 공식 SDK보다 느려졌습니다. 반대로 공식 SDK에서 Python의 `RecordResult` 포장만 건너뛰고 같은 네이티브 recordset에서 모든 bins를 읽으면 일반 빌드의 시간은 336.44 ms에서 320.21 ms로 줄었습니다. 두 실험에서 가장 큰 차이를 만든 것은 비동기 경계를 오간 횟수였습니다.

## Free-threaded 빌드에서 격차가 줄어드는 이유 {#why-the-gap-narrows-on-the-free-threaded-build}

공식 네이티브 클라이언트는 Unix에서 uvloop를 쓸 때 일반 wheel에서는 `loop.call_soon_threadsafe()`를, free-threaded wheel에서는 기본적으로 소켓 쌍을 사용합니다. 후자의 경우 waker 스레드가 소켓에 한 바이트를 쓰고 이벤트 루프에 등록된 reader가 완료 큐를 처리합니다. wheel의 빌드 플래그에 따라 기본값을 고르므로, free-threaded wheel에서 GIL을 다시 켜도 소켓 쌍을 선택합니다. [알림 방식 선택](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/completion.rs#L196-L229) · [Waker 스레드](https://github.com/aerospike/aerospike-client-python-native/blob/146d28baa3f579f54b8de43b1062330ecaf6a71e/src/waker.rs#L118-L179)

환경 변수 `AEROSPIKE_PIPE_WAKE=0`과 `=1`로 알림 방식을 각각 고정하고 확장을 import한 뒤 실제 GIL 상태를 확인했습니다. 각 칸은 새 프로세스에서 5회 측정한 경과 시간의 중앙값입니다.

| 공식 SDK 실행 조건 | `call_soon_threadsafe` | 소켓 쌍 |
|---|---:|---:|
| 일반 wheel, GIL 켜짐 | 336.31 ms | 202.89 ms |
| Free-threaded wheel, GIL 다시 켬 | 343.09 ms | 199.28 ms |
| Free-threaded wheel, GIL 꺼짐 | 336.61 ms | 199.56 ms |

일반 wheel에서 깨우는 방식만 바꿔도 **133 ms**가 줄었습니다. 같은 free-threaded wheel에서 소켓 쌍을 쓰도록 고정하면 GIL을 켜거나 끈 결과가 모두 약 **199 ms**였습니다. 별도 프로파일링에서 SDK의 클라이언트 전체 CPU는 스캔당 일반 247.84 ms와 free-threaded 242.30 ms로 비슷했고 경과 시간은 단축됐습니다. 이 수치는 위 Unix·uvloop 환경에서 단일 스트림을 읽었을 때의 결과입니다.

aerospike-py 자체의 시간도 변했습니다. 별도 실험에서 스캔 한 번의 시간을 48번의 묶음 보충 호출 안팎으로 나눴습니다. 7회 산술평균으로 볼 때 보충 구간은 일반 **25.07 ms → free-threaded 28.61 ms**, 나머지 구간은 **8.46 → 15.59 ms**였습니다. 나머지 시간에는 Python 반복, 레코드 포장, 값 검산과 객체 해제가 함께 포함됩니다.

### 진단용 빌드에서 확인한 행별 로깅 비용 {#per-record-logging-in-a-diagnostic-build}

측정 대상 커밋은 Python 루트 로그 수준이 `WARNING`이어도 레코드를 변환할 때마다 Rust의 `trace!` 호출을 Python logging에 전달합니다. 별도 진단용 빌드에서 그 호출 한 곳만 생략하자, 12,000행의 Rust → Python 변환 시간 중앙값은 일반 CPython에서 **9.52 → 1.80 ms**, free-threaded에서 **10.36 → 2.06 ms**로 줄었습니다. 위의 release wheel 비교 결과에는 기존 로깅 경로가 포함돼 있습니다. [레코드 변환](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/types/record.rs#L41-L71) · [로깅 브리지](https://github.com/aerospike-ce-ecosystem/aerospike-py/blob/4aabf09f7ca1911a5ba00a3d668ec799c19ed54c/rust/src/logging.rs#L75-L104)

<a href={useBaseUrl('/benchmark/4aabf09/async-stream-profile.zip')}>측정값·프로파일링 스크립트·재현 방법 다운로드 (ZIP)</a>
