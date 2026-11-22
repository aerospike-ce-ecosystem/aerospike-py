---
title: 0.15 벤치마크 · 배치 연산과 쿼리
sidebar_label: 배치 연산과 쿼리
sidebar_position: 2
slug: /performance/client-comparison
description: aerospike-py 0.15, aerospike-py 0.14.4와 공식 Python SDK의 서버 배치, NumPy, 전체 조회, 독립 단건 요청 성능을 비교합니다.
---

import useBaseUrl from '@docusaurus/useBaseUrl';

aerospike-py 0.15 후보판(`4aabf09`)을 **직전 버전 0.14.4**, **공식 Aerospike Python SDK 1.0.0**(`aerospike-sdk`)과 비교했습니다. [로컬 측정 조건](#measurement-conditions)

## 720키 서버 배치 {#server-batches-with-720-keys}

4개 스레드가 동기 클라이언트 하나를 공유했습니다. 각 스레드는 자신에게 할당된 기존 정수 키 720개를 반복해서 사용했고, 키마다 정수 bin 8개를 저장했습니다. 읽기에서는 8개 값을 모두 검산했습니다. 쓰기에서는 키마다 다른 값을 기록하고 모든 행의 결과 코드를 확인한 뒤, 측정 종료 후 다시 읽어 저장값을 검증했습니다. 처리량 단위는 **초당 천 행**입니다.

| Python 빌드 | 입력 또는 출력 | 0.14.4 | 0.15 | 공식 SDK |
|---|---|---:|---:|---:|
| 일반 | 읽기 → dict | 258.1 | 271.8 | 228.1 |
| 일반 | dict → 쓰기 | 190.4 | 204.7 | 176.8 |
| 일반 | 읽기 → NumPy 배열 | 249.4 | 283.6 | 211.2 |
| 일반 | NumPy 배열 → 쓰기 | 188.3 | 222.0 | 187.2 |
| Free-threaded | 읽기 → dict | 252.0 | 260.3 | 250.2 |
| Free-threaded | dict → 쓰기 | 167.3 | 163.4 | 195.5 |
| Free-threaded | 읽기 → NumPy 배열 | 253.1 | 300.7 | 256.3 |
| Free-threaded | NumPy 배열 → 쓰기 | 192.3 | 214.7 | 183.9 |

aerospike-py 두 버전에서는 `batch_read().to_list()`, `to_numpy(dtype)`, `batch_write()`, `batch_write_numpy()`를 사용했습니다. 공식 SDK에서는 `session.query(*keys).execute()`의 결과를 `collect()`로 읽고, `session.upsert(dataset).bins(...).rows(...).execute()`로 썼습니다. dict 쓰기에는 준비된 키와 행별 dict로 각 클라이언트의 요청을 만드는 시간도 포함됩니다. 공식 SDK의 NumPy 읽기에는 `numpy.fromiter()`로 출력 배열을 만드는 시간, 쓰기에는 `tolist()`로 입력 배열을 변환하는 시간이 포함됩니다.

- Free-threaded NumPy 읽기에서 행당 클라이언트 CPU 시간은 **0.15 2.26µs**, 0.14.4 2.43µs, 공식 SDK 4.97µs였습니다. 배치 호출의 p99는 **공식 SDK가 22.6ms**로 가장 짧았고, 0.15 26.8ms, 0.14.4 29.6ms였습니다.
- 각 API에 맞는 쓰기 입력을 미리 만들어 재사용했을 때 일반 빌드의 처리량(천 행/초)은 0.14.4 / 0.15 / 공식 SDK 순서로 189.8 / 204.9 / 190.7이었습니다. Free-threaded에서는 같은 순서로 162.0 / 163.8 / 194.1이었습니다.
- 호출 스레드가 하나이면 일반 Python의 dict 읽기 처리량(천 행/초)은 0.14.4 / 0.15 / 공식 SDK 순서로 104.2 / 103.8 / 98.5였습니다. 스레드 4개일 때 나타난 0.15와 0.14.4의 차이가 스레드 하나에서는 1% 미만으로 줄었습니다.

## 전체 조회 {#full-set-queries}

소비자 하나가 레코드 12,000개를 끝까지 읽었습니다. 각 레코드의 정수 ID와 160바이트 문자열을 검산하고 중복·누락을 확인했습니다. 표의 시간은 **전체 결과를 소비하는 데 걸린 밀리초**입니다. 목록 수집에는 aerospike-py의 `query.results()`와 공식 SDK 쿼리 결과의 `collect()`를, 비동기 순회에는 `async for`를 사용했습니다.

| Python 빌드 | 결과 소비 방식 | 0.14.4 | 0.15 | 공식 SDK |
|---|---|---:|---:|---:|
| 일반 | 동기 목록 수집 | 43.16 | 34.71 | 25.04 |
| 일반 | 비동기 목록 수집 | 47.70 | 29.23 | 339.97 |
| 일반 | 비동기 iterator | — | 33.75 | 336.53 |
| Free-threaded | 동기 목록 수집 | 46.86 | 36.63 | 28.62 |
| Free-threaded | 비동기 목록 수집 | 46.68 | 36.12 | 191.88 |
| Free-threaded | 비동기 iterator | — | 41.80 | 196.64 |

동기 목록 수집은 두 빌드 모두 공식 SDK가 가장 빨랐습니다. 비동기 목록 수집에서 0.15는 0.14.4보다 일반 빌드에서 **38.7%**, free-threaded에서 **22.6%** 짧은 시간에 끝났습니다. 0.14.4는 비동기 `foreach()` 콜백을 제공했고, 0.15에서 공개 비동기 iterator가 추가됐습니다. iterator끼리 비교한 공식 SDK의 소요 시간은 일반 빌드에서 0.15의 **9.97배**, free-threaded에서 **4.70배**였습니다. [비동기 스트림 프로파일](./async-stream-profile.md)

## 독립 단건 요청 {#independent-point-operations}

키마다 독립적인 명령을 실행하려면 aerospike-py에서 여러 `get()` 또는 `put()`을 `asyncio.gather()`로 호출할 수 있습니다. 공식 SDK의 `get_many()`와 `put_many()`는 독립적인 명령 여러 개를 한 번의 호출로 제출합니다. 이 실험에서는 **32키 묶음을 한 번에 하나씩** 처리했습니다. 쓰기는 한 묶음의 모든 키에 같은 8개 bin 값을 기록했습니다. 처리량 단위는 **초당 천 행**입니다. [공식 SDK 단건 묶음 구현](https://github.com/aerospike/aerospike-client-python-sdk/blob/v1.0.0/aerospike_sdk/aio/session.py#L460-L558)

| Python 빌드 | 작업 | 0.14.4 | 0.15 | 공식 SDK |
|---|---|---:|---:|---:|
| 일반 | 읽기 | 22.28 | 22.02 | 25.02 |
| 일반 | 쓰기 | 22.98 | 22.42 | 25.39 |
| Free-threaded | 읽기 | 18.20 | 17.35 | 25.48 |
| Free-threaded | 쓰기 | 19.32 | 19.01 | 26.30 |

Free-threaded에서 독립 단건을 읽을 때 행당 클라이언트 CPU 시간은 **공식 SDK 18.55µs**, 0.14.4 260.19µs, 0.15 258.19µs였습니다. 여러 키를 처리하는 애플리케이션에서는 각 키에 독립 명령을 보내는지, 서버 배치로 보내는지에 따라 적용할 수치가 달라집니다.

## 측정 환경 {#measurement-conditions}

12코어 Apple M4 Pro(메모리 24GiB)에서 클라이언트와 단일 노드 Aerospike CE 8.2.0.1이 CPU를 공유했습니다. 서버는 5 vCPU의 Podman VM에서 실행했습니다. CPython 3.14.2와 3.14.2t, NumPy 2.5.5를 사용했고 비동기 작업에는 uvloop 0.23.0을 사용했습니다. 각 프로세스에서 클라이언트를 import한 뒤 실제 GIL 상태를 확인했습니다.

표의 수치는 클라이언트 실행 순서를 바꾸어 세 번 측정한 중앙값입니다. 워밍업 후 서버 배치는 조건당 1.2초, 독립 단건 묶음은 조건당 1.5초 측정했습니다. 전체 조회는 회차마다 워밍업 조회 뒤 한 번을 측정했습니다. 행당 CPU에는 클라이언트 프로세스의 모든 스레드가 포함됩니다. 배치 p99는 720행을 처리하는 호출 한 번의 지연입니다. 서버와 클라이언트가 호스트를 공유한 단시간 실험이므로 작은 차이를 실제 클러스터의 성능 차이로 일반화하기는 어렵습니다.

<a href={useBaseUrl('/benchmark/4aabf09/client-comparison.zip')}>측정값·스크립트·재현 절차 내려받기 (ZIP)</a>
