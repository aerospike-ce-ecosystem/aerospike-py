---
name: project-goals
description: Defines aerospike-py project goals and provides a plan review checklist. Used to verify goal alignment when creating plans.
user-invocable: false
model: opus
---

# Project Goals

A high-performance client library that wraps aerospike-client-rust v2 as Python bindings via PyO3.

## 5 Core Goals

| # | Goal | Key Metric |
|---|------|----------|
| 1 | **Rust v2 Bindings** | Expose aerospike crate 2.x API via both sync/async paths |
| 2 | **Performance** | GIL-free I/O, outperform C client (aerospike-client-python) on async paths |
| 3 | **Observability** | logging · OTel tracing · Prometheus metrics |
| 4 | **NumPy v2 Integration** | Direct structured array I/O for batch read/write |
| 5 | **Type-based Objects** | NamedTuple returns, TypedDict policies, complete `.pyi` stubs |

Detailed status and implementation guides: `reference/goal-{1..5}-*.md`
Unresolved tasks: `reference/backlog.md`

## Plan Review Checklist

Verify the following after writing a plan:

- [ ] Does it contribute to at least one of the 5 core goals?
- [ ] **Rust first**: Is the core logic in Rust with Python as a thin wrapper?
- [ ] **GIL safety**: Does it follow `py.detach()` for sync and `future_into_py()` for async?
- [ ] Is it consistent with existing API patterns? (see `new-api` skill)
- [ ] **Zero Python deps**: Does the default installation avoid adding external Python dependencies?
- [ ] Are `.pyi` type stubs updated alongside the implementation?
- [ ] Are there no excessive changes beyond the goal scope?
