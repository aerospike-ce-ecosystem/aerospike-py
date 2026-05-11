// VU 100 isolated load — used to capture clean CPU% / latency at the
// saturation point of interest (issue #347 reports VU 100 = 100% CPU for
// aerospike-py vs 62% for the C ext at matched latency).
//
// Runs warmup → VU 100 plateau for 90s. Total ~110s.

import http from "k6/http";
import { check } from "k6";
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
    vu_100: {
      executor: "constant-vus",
      vus: 100,
      duration: "90s",
      exec: "predict",
      tags: { phase: "vu_100" },
      startTime: "20s",
    },
  },
  thresholds: {
    errors: ["rate<0.01"],
  },
};

export function predict() {
  const res = http.post(`${BASE_URL}/predict`, null, { timeout: "30s" });
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
    } catch (_e) {}
  }
}
