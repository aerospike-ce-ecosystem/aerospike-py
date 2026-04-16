# ASGI Benchmark Report — 2026-04-16 13:53:12

## Conditions

| Item | Value |
|------|-------|
| Clients | official, py-async |
| Iterations | 200 |
| Concurrency | 10 |

## Pipeline Breakdown

| client | total mean(ms) | p50 | p90 | p95 | p99 | aerospike(ms) | inference(ms) | http(ms) | tps | errors |
|--------|----------------|-----|-----|-----|-----|---------------|---------------|----------|-----|--------|
| official | 465.81 | 413.27 | 718.78 | 885.64 | 2450.38 | 460.49 | 1.00 | 479.44 | 20.9 | 0 |
| py-async | 580.70 | 539.13 | 903.09 | 986.93 | 1000.99 | 575.35 | 1.08 | 720.45 | 13.9 | 56 |

## Comparison

- **Latency**: py-async is 0.8x faster
- **Throughput**: py-async is 0.7x higher
- **Aerospike**: official=460.49ms vs py-async=575.35ms
- **Inference**: official=1.00ms vs py-async=1.08ms
