# ASGI Benchmark Report — 2026-04-16 13:47:40

## Conditions

| Item | Value |
|------|-------|
| Clients | official, py-async |
| Iterations | 50 |
| Concurrency | 5 |

## Pipeline Breakdown

| client | total mean(ms) | p50 | p90 | p95 | p99 | aerospike(ms) | inference(ms) | http(ms) | tps | errors |
|--------|----------------|-----|-----|-----|-----|---------------|---------------|----------|-----|--------|
| official | 289.56 | 289.36 | 429.74 | 461.15 | 473.60 | 280.00 | 1.55 | 300.69 | 16.6 | 0 |
| py-async | 228.49 | 189.56 | 457.42 | 468.03 | 497.09 | 221.12 | 1.46 | 258.10 | 19.4 | 1 |

## Comparison

- **Latency**: py-async is 1.3x faster
- **Throughput**: py-async is 1.2x higher
- **Aerospike**: official=280.00ms vs py-async=221.12ms
- **Inference**: official=1.55ms vs py-async=1.46ms
