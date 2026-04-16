# Benchmark Report — 2026-04-16 13:45:25

## Conditions

| Item | Value |
|------|-------|
| Clients | official, official-async, py-async |
| Sets | 9 |
| Batch sizes | [50, 200] |
| Concurrency | 10 |
| Iterations | 30 |

## Results

| client | set | batch | conc | mean(ms) | p50 | p90 | p95 | p99 | tps | found% | cv |
|--------|-----|-------|------|----------|-----|-----|-----|-----|-----|--------|----|
| official | nccsh_adid | 50 | 10 | 110.23 | 95.29 | 174.14 | 183.59 | 200.14 | 89.4 | 86.0% | 0.318 |
| py-async | nccsh_adid | 50 | 10 | 19.74 | 14.59 | 24.94 | 38.39 | 105.46 | 382.6 | 86.0% | 0.922 |
| official-async | nccsh_adid | 50 | 10 | 118.02 | 99.75 | 181.64 | 204.24 | 220.14 | 83.8 | 86.0% | 0.338 |
| official | nccsh_adid | 200 | 10 | 127.06 | 107.44 | 192.51 | 198.80 | 206.19 | 77.1 | 82.0% | 0.308 |
| official-async | nccsh_adid | 200 | 10 | 133.62 | 114.71 | 194.93 | 196.94 | 203.95 | 72.9 | 82.0% | 0.290 |
| py-async | nccsh_adid | 200 | 10 | 30.53 | 20.26 | 38.56 | 145.50 | 194.05 | 261.1 | 82.0% | 1.212 |
| py-async | nccsh_adgroupid | 50 | 10 | 15.57 | 13.66 | 20.60 | 23.17 | 34.68 | 472.1 | 92.0% | 0.498 |
| official-async | nccsh_adgroupid | 50 | 10 | 118.21 | 98.32 | 185.18 | 190.71 | 252.05 | 83.0 | 92.0% | 0.364 |
| official | nccsh_adgroupid | 50 | 10 | 121.76 | 101.15 | 180.75 | 195.52 | 210.24 | 81.1 | 92.0% | 0.316 |
| py-async | nccsh_adgroupid | 200 | 10 | 24.98 | 19.28 | 31.72 | 61.83 | 124.86 | 281.3 | 89.5% | 0.870 |
| official | nccsh_adgroupid | 200 | 10 | 110.86 | 95.41 | 172.60 | 176.38 | 194.82 | 89.0 | 89.5% | 0.298 |
| official-async | nccsh_adgroupid | 200 | 10 | 123.70 | 99.04 | 193.06 | 205.07 | 221.90 | 79.3 | 89.5% | 0.355 |
| official | nccsh_campaignid | 50 | 10 | 108.00 | 90.92 | 171.16 | 179.05 | 184.32 | 91.3 | 70.0% | 0.315 |
| py-async | nccsh_campaignid | 50 | 10 | 18.53 | 14.61 | 19.51 | 40.14 | 103.22 | 479.8 | 70.0% | 0.877 |
| official-async | nccsh_campaignid | 50 | 10 | 115.06 | 94.89 | 189.24 | 203.22 | 239.85 | 85.8 | 70.0% | 0.371 |
| official-async | nccsh_campaignid | 200 | 10 | 115.02 | 96.39 | 182.17 | 187.48 | 237.61 | 85.7 | 64.5% | 0.349 |
| official | nccsh_campaignid | 200 | 10 | 128.85 | 106.23 | 194.90 | 215.29 | 220.15 | 76.5 | 64.5% | 0.329 |
| py-async | nccsh_campaignid | 200 | 10 | 23.35 | 16.86 | 26.03 | 100.99 | 110.90 | 306.1 | 64.5% | 0.903 |
| py-async | nccsh_adid_channelid | 50 | 10 | 18.18 | 13.66 | 20.34 | 42.02 | 116.92 | 474.2 | 84.0% | 1.044 |
| official-async | nccsh_adid_channelid | 50 | 10 | 109.09 | 89.99 | 171.54 | 174.66 | 187.78 | 90.2 | 84.0% | 0.327 |
| official | nccsh_adid_channelid | 50 | 10 | 109.15 | 91.30 | 182.67 | 190.38 | 206.11 | 89.3 | 84.0% | 0.352 |
| official-async | nccsh_adid_channelid | 200 | 10 | 124.35 | 99.11 | 189.13 | 215.24 | 228.73 | 79.0 | 57.5% | 0.353 |
| official | nccsh_adid_channelid | 200 | 10 | 118.69 | 98.56 | 189.57 | 190.10 | 195.77 | 81.2 | 57.5% | 0.317 |
| py-async | nccsh_adid_channelid | 200 | 10 | 23.12 | 17.88 | 34.26 | 58.64 | 109.32 | 283.9 | 57.5% | 0.780 |
| py-async | nccsh_adgroupid_channelid | 50 | 10 | 25.57 | 14.12 | 23.54 | 102.73 | 301.28 | 258.4 | 82.0% | 1.746 |
| official | nccsh_adgroupid_channelid | 50 | 10 | 113.21 | 94.64 | 177.26 | 187.42 | 195.27 | 86.7 | 82.0% | 0.304 |
| official-async | nccsh_adgroupid_channelid | 50 | 10 | 117.54 | 96.45 | 188.41 | 194.60 | 228.28 | 81.9 | 82.0% | 0.351 |
| py-async | nccsh_adgroupid_channelid | 200 | 10 | 26.85 | 19.94 | 28.20 | 112.48 | 148.11 | 297.8 | 76.5% | 1.040 |
| official-async | nccsh_adgroupid_channelid | 200 | 10 | 115.15 | 97.66 | 180.50 | 186.38 | 199.36 | 83.6 | 76.5% | 0.304 |
| official | nccsh_adgroupid_channelid | 200 | 10 | 122.26 | 107.30 | 191.11 | 197.81 | 197.89 | 78.8 | 76.5% | 0.298 |
| official-async | nccsh_campaignid_channelid | 50 | 10 | 115.39 | 97.46 | 183.84 | 186.53 | 188.71 | 84.7 | 70.0% | 0.329 |
| official | nccsh_campaignid_channelid | 50 | 10 | 115.30 | 95.18 | 185.92 | 200.86 | 210.74 | 84.8 | 70.0% | 0.353 |
| py-async | nccsh_campaignid_channelid | 50 | 10 | 18.87 | 14.86 | 21.93 | 38.56 | 103.98 | 443.4 | 70.0% | 0.890 |
| official | nccsh_campaignid_channelid | 200 | 10 | 123.93 | 103.90 | 188.30 | 209.71 | 261.41 | 79.4 | 62.5% | 0.365 |
| official-async | nccsh_campaignid_channelid | 200 | 10 | 127.50 | 100.67 | 195.56 | 207.06 | 217.53 | 76.8 | 62.5% | 0.336 |
| py-async | nccsh_campaignid_channelid | 200 | 10 | 30.47 | 23.85 | 35.42 | 107.82 | 122.36 | 286.8 | 62.5% | 0.790 |
| official-async | nccsh_nvmid | 50 | 10 | 122.61 | 102.28 | 191.44 | 193.51 | 237.64 | 80.2 | 98.0% | 0.330 |
| py-async | nccsh_nvmid | 50 | 10 | 17.83 | 15.71 | 23.85 | 26.97 | 44.86 | 430.0 | 98.0% | 0.515 |
| official | nccsh_nvmid | 50 | 10 | 115.34 | 95.69 | 181.36 | 182.70 | 190.68 | 85.4 | 98.0% | 0.333 |
| official-async | nccsh_nvmid | 200 | 10 | 131.88 | 110.98 | 193.00 | 195.71 | 228.31 | 69.5 | 90.0% | 0.320 |
| official | nccsh_nvmid | 200 | 10 | 126.81 | 104.10 | 202.45 | 210.08 | 215.87 | 77.3 | 90.0% | 0.328 |
| py-async | nccsh_nvmid | 200 | 10 | 41.17 | 33.98 | 65.92 | 117.43 | 133.61 | 162.3 | 90.0% | 0.658 |
| official-async | nccsh_userid | 50 | 10 | 17.76 | 13.34 | 19.10 | 50.62 | 100.97 | 517.4 | 0.0% | 0.954 |
| py-async | nccsh_userid | 50 | 10 | 15.20 | 11.29 | 17.46 | 26.75 | 97.95 | 586.7 | 0.0% | 1.045 |
| official | nccsh_userid | 50 | 10 | 13.92 | 10.75 | 13.89 | 18.47 | 96.27 | 686.1 | 0.0% | 1.108 |
| official-async | nccsh_userid | 200 | 10 | 20.21 | 16.94 | 21.14 | 38.96 | 101.99 | 459.9 | 0.0% | 0.785 |
| official | nccsh_userid | 200 | 10 | 19.95 | 17.03 | 20.21 | 23.60 | 102.12 | 475.1 | 0.0% | 0.775 |
| py-async | nccsh_userid | 200 | 10 | 16.27 | 12.28 | 17.15 | 20.86 | 116.03 | 488.8 | 0.0% | 1.148 |
| official-async | nccsh_hconvvalue_nvmid | 50 | 10 | 117.07 | 93.98 | 178.66 | 209.53 | 223.40 | 84.0 | 98.0% | 0.355 |
| official | nccsh_hconvvalue_nvmid | 50 | 10 | 111.80 | 92.75 | 173.22 | 182.74 | 217.14 | 87.8 | 98.0% | 0.349 |
| py-async | nccsh_hconvvalue_nvmid | 50 | 10 | 16.92 | 13.53 | 18.70 | 23.61 | 95.59 | 489.8 | 98.0% | 0.897 |
| py-async | nccsh_hconvvalue_nvmid | 200 | 10 | 20.95 | 14.82 | 37.71 | 49.47 | 108.81 | 342.5 | 84.0% | 0.951 |
| official | nccsh_hconvvalue_nvmid | 200 | 10 | 139.05 | 121.53 | 195.04 | 201.73 | 210.95 | 70.7 | 84.0% | 0.328 |
| official-async | nccsh_hconvvalue_nvmid | 200 | 10 | 149.35 | 165.83 | 208.60 | 217.90 | 285.82 | 64.6 | 84.0% | 0.340 |

## official vs py-async

| set | batch | official mean | official p99 | py-async mean | py-async p99 | mean speedup | p99 speedup | tps speedup |
|-----|-------|-------------|------------|--------------|-------------|--------------|-------------|-------------|
| nccsh_adid | 50 | 110.23ms | 200.14ms | 19.74ms | 105.46ms | 5.6x | 1.9x | 4.3x |
| nccsh_adid | 200 | 127.06ms | 206.19ms | 30.53ms | 194.05ms | 4.2x | 1.1x | 3.4x |
| nccsh_adgroupid | 50 | 121.76ms | 210.24ms | 15.57ms | 34.68ms | 7.8x | 6.1x | 5.8x |
| nccsh_adgroupid | 200 | 110.86ms | 194.82ms | 24.98ms | 124.86ms | 4.4x | 1.6x | 3.2x |
| nccsh_campaignid | 50 | 108.00ms | 184.32ms | 18.53ms | 103.22ms | 5.8x | 1.8x | 5.3x |
| nccsh_campaignid | 200 | 128.85ms | 220.15ms | 23.35ms | 110.90ms | 5.5x | 2.0x | 4.0x |
| nccsh_adid_channelid | 50 | 109.15ms | 206.11ms | 18.18ms | 116.92ms | 6.0x | 1.8x | 5.3x |
| nccsh_adid_channelid | 200 | 118.69ms | 195.77ms | 23.12ms | 109.32ms | 5.1x | 1.8x | 3.5x |
| nccsh_adgroupid_channelid | 50 | 113.21ms | 195.27ms | 25.57ms | 301.28ms | 4.4x | 0.6x | 3.0x |
| nccsh_adgroupid_channelid | 200 | 122.26ms | 197.89ms | 26.85ms | 148.11ms | 4.6x | 1.3x | 3.8x |
| nccsh_campaignid_channelid | 50 | 115.30ms | 210.74ms | 18.87ms | 103.98ms | 6.1x | 2.0x | 5.2x |
| nccsh_campaignid_channelid | 200 | 123.93ms | 261.41ms | 30.47ms | 122.36ms | 4.1x | 2.1x | 3.6x |
| nccsh_nvmid | 50 | 115.34ms | 190.68ms | 17.83ms | 44.86ms | 6.5x | 4.3x | 5.0x |
| nccsh_nvmid | 200 | 126.81ms | 215.87ms | 41.17ms | 133.61ms | 3.1x | 1.6x | 2.1x |
| nccsh_userid | 50 | 13.92ms | 96.27ms | 15.20ms | 97.95ms | 0.9x | 1.0x | 0.9x |
| nccsh_userid | 200 | 19.95ms | 102.12ms | 16.27ms | 116.03ms | 1.2x | 0.9x | 1.0x |
| nccsh_hconvvalue_nvmid | 50 | 111.80ms | 217.14ms | 16.92ms | 95.59ms | 6.6x | 2.3x | 5.6x |
| nccsh_hconvvalue_nvmid | 200 | 139.05ms | 210.95ms | 20.95ms | 108.81ms | 6.6x | 1.9x | 4.8x |

## official-async vs py-async

| set | batch | official-async mean | official-async p99 | py-async mean | py-async p99 | mean speedup | p99 speedup | tps speedup |
|-----|-------|-------------|------------|--------------|-------------|--------------|-------------|-------------|
| nccsh_adid | 50 | 118.02ms | 220.14ms | 19.74ms | 105.46ms | 6.0x | 2.1x | 4.6x |
| nccsh_adid | 200 | 133.62ms | 203.95ms | 30.53ms | 194.05ms | 4.4x | 1.1x | 3.6x |
| nccsh_adgroupid | 50 | 118.21ms | 252.05ms | 15.57ms | 34.68ms | 7.6x | 7.3x | 5.7x |
| nccsh_adgroupid | 200 | 123.70ms | 221.90ms | 24.98ms | 124.86ms | 5.0x | 1.8x | 3.5x |
| nccsh_campaignid | 50 | 115.06ms | 239.85ms | 18.53ms | 103.22ms | 6.2x | 2.3x | 5.6x |
| nccsh_campaignid | 200 | 115.02ms | 237.61ms | 23.35ms | 110.90ms | 4.9x | 2.1x | 3.6x |
| nccsh_adid_channelid | 50 | 109.09ms | 187.78ms | 18.18ms | 116.92ms | 6.0x | 1.6x | 5.3x |
| nccsh_adid_channelid | 200 | 124.35ms | 228.73ms | 23.12ms | 109.32ms | 5.4x | 2.1x | 3.6x |
| nccsh_adgroupid_channelid | 50 | 117.54ms | 228.28ms | 25.57ms | 301.28ms | 4.6x | 0.8x | 3.2x |
| nccsh_adgroupid_channelid | 200 | 115.15ms | 199.36ms | 26.85ms | 148.11ms | 4.3x | 1.3x | 3.6x |
| nccsh_campaignid_channelid | 50 | 115.39ms | 188.71ms | 18.87ms | 103.98ms | 6.1x | 1.8x | 5.2x |
| nccsh_campaignid_channelid | 200 | 127.50ms | 217.53ms | 30.47ms | 122.36ms | 4.2x | 1.8x | 3.7x |
| nccsh_nvmid | 50 | 122.61ms | 237.64ms | 17.83ms | 44.86ms | 6.9x | 5.3x | 5.4x |
| nccsh_nvmid | 200 | 131.88ms | 228.31ms | 41.17ms | 133.61ms | 3.2x | 1.7x | 2.3x |
| nccsh_userid | 50 | 17.76ms | 100.97ms | 15.20ms | 97.95ms | 1.2x | 1.0x | 1.1x |
| nccsh_userid | 200 | 20.21ms | 101.99ms | 16.27ms | 116.03ms | 1.2x | 0.9x | 1.1x |
| nccsh_hconvvalue_nvmid | 50 | 117.07ms | 223.40ms | 16.92ms | 95.59ms | 6.9x | 2.3x | 5.8x |
| nccsh_hconvvalue_nvmid | 200 | 149.35ms | 285.82ms | 20.95ms | 108.81ms | 7.1x | 2.6x | 5.3x |

## Summary

- **official**: avg mean=107.56ms, avg p99=195.34ms, avg tps=138.2
- **official-async**: avg mean=110.64ms, avg p99=211.33ms, avg tps=125.7
- **py-async**: avg mean=22.45ms, avg p99=120.67ms, avg tps=373.7
- **py-async vs official**: 4.8x faster latency, 2.7x higher throughput
- **py-async vs official-async**: 4.9x faster latency, 3.0x higher throughput
