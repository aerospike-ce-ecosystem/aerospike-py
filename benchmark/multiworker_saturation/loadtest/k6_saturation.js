// Saturation ramp for issue #347.
//
// 5 plateaus × 90 s each (after a 15 s warmup). Each plateau holds VU
// steady so we get clean RPS/latency for one operating point. We do NOT
// use ramping-vus across the whole run because we want each VU level
// to be a separately analyzable measurement point.
//
// Run:
//   BASE_URL=http://127.0.0.1:8000 \
//   k6 run --summary-export results/<run>/k6_summary.json loadtest/k6_saturation.js

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

const latency = new Trend("endpoint_latency_ms", true);
const dbLatency = new Trend("db_latency_ms", true);
const errors = new Rate("errors");
const reqs = new Counter("predict_requests");

export const options = {
  discardResponseBodies: false,
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 2,
      duration: "15s",
      exec: "predict",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    vu_10: {
      executor: "constant-vus",
      vus: 10,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_10" },
      startTime: "20s",
    },
    vu_50: {
      executor: "constant-vus",
      vus: 50,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_50" },
      startTime: "115s",
    },
    vu_100: {
      executor: "constant-vus",
      vus: 100,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_100" },
      startTime: "210s",
    },
    vu_150: {
      executor: "constant-vus",
      vus: 150,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_150" },
      startTime: "305s",
    },
    vu_200: {
      executor: "constant-vus",
      vus: 200,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_200" },
      startTime: "400s",
    },
  },
  thresholds: {
    errors: ["rate<0.01"],
  },
};

export function predict() {
  const res = http.post(`${BASE_URL}/predict`, null, {
    timeout: "30s",
  });
  reqs.add(1);
  const ok = check(res, { "status 200": (r) => r.status === 200 });
  errors.add(!ok);
  if (ok) {
    latency.add(res.timings.duration);
    try {
      const body = res.json();
      if (body && typeof body.db_elapsed_ms === "number") {
        dbLatency.add(body.db_elapsed_ms);
      }
    } catch (_e) {
      // ignore parse failures — already counted in errors
    }
  }
}
