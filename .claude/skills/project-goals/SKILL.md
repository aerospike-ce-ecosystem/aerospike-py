---
name: project-goals
description: aerospike-py 프로젝트 목표 정의 및 plan 검토 체크리스트. plan 생성 시 목표 정합성 검토에 사용.
user-invocable: false
model: opus
---

# Project Goals

aerospike-client-rust v2를 PyO3로 Python 바인딩하는 고성능 클라이언트 라이브러리.

## 5대 목표

| # | 목표 | 핵심 지표 |
|---|------|----------|
| 1 | **Rust v2 바인딩** | aerospike crate 2.x API를 sync/async 양쪽으로 노출 |
| 2 | **성능** | GIL-free I/O, async 경로에서 C 클라이언트(aerospike-client-python) 대비 우위 |
| 3 | **Observability** | logging · OTel tracing · Prometheus metrics |
| 4 | **NumPy v2 통합** | 배치 read/write에서 structured array 직접 입출력 |
| 5 | **Type 기반 객체** | NamedTuple 반환, TypedDict 정책, `.pyi` 완비 |

상세 현황 및 구현 가이드: `reference/goal-{1..5}-*.md`
미해결 과제: `reference/backlog.md`

## Plan 검토 체크리스트

plan 작성 후 아래 항목을 확인한다:

- [ ] 5대 목표 중 하나 이상에 기여하는가?
- [ ] **Rust 우선**: 핵심 로직이 Rust에 있고 Python은 얇은 래퍼인가?
- [ ] **GIL 안전**: sync는 `py.detach()`, async는 `future_into_py()` 패턴을 따르는가?
- [ ] 기존 API 패턴과 일관성이 있는가? (`new-api` 스킬 참조)
- [ ] **Zero Python dep**: 기본 설치 시 외부 Python 의존성이 추가되지 않는가?
- [ ] `.pyi` 타입 스텁이 함께 업데이트되는가?
- [ ] 목표 범위를 벗어나는 과도한 변경이 없는가?
