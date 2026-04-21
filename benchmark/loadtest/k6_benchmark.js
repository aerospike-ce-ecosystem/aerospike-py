import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// Custom metrics — default (single mode after optimization)
const officialLatency = new Trend("official_latency_ms");
const pyAsyncLatency = new Trend("py_async_latency_ms");
// Comparison — gather mode (baseline, before optimization)
const officialGatherLatency = new Trend("official_gather_ms");
const pyAsyncGatherLatency = new Trend("py_async_gather_ms");

// Stress metrics (separate from comparison)
const pyAsyncStressLatency = new Trend("py_async_stress_ms");
const errorRate = new Rate("error_rate");

// Configuration
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const HOST = __ENV.HOST || "";
const HEADERS = HOST ? { headers: { Host: HOST } } : {};

export const options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 2,
      duration: "10s",
      exec: "warmup",
      startTime: "0s",
    },
    // single mode (default — optimized)
    single: {
      executor: "constant-vus",
      vus: 10,
      duration: "60s",
      exec: "singleTest",
      startTime: "15s",
    },
    // gather mode (comparison baseline)
    gather: {
      executor: "constant-vus",
      vus: 10,
      duration: "60s",
      exec: "gatherTest",
      startTime: "80s",
    },
    // stress test (single mode, ramp up)
    stress: {
      executor: "ramping-vus",
      stages: [
        { duration: "30s", target: 20 },
        { duration: "60s", target: 50 },
        { duration: "30s", target: 0 },
      ],
      exec: "stressTest",
      startTime: "145s",
    },
  },
  thresholds: {
    "py_async_latency_ms": ["p(90)<200", "p(95)<300"],
    "official_latency_ms": ["p(90)<400", "p(95)<500"],
    error_rate: ["rate<0.02"],
  },
};

function get(path) {
  return http.get(`${BASE_URL}${path}`, HEADERS);
}

function record(resp, metric) {
  if (resp.status === 200) {
    metric.add(JSON.parse(resp.body).total_ms);
  } else {
    errorRate.add(1);
  }
}

export function warmup() {
  get("/predict/py-async/sample?skip_inference=true");
  sleep(0.5);
}

export function singleTest() {
  // default mode is now single
  const r1 = get("/predict/official/sample");
  check(r1, { "official 200": (r) => r.status === 200 });
  record(r1, officialLatency);
  sleep(0.05);

  const r2 = get("/predict/py-async/sample");
  check(r2, { "py-async 200": (r) => r.status === 200 });
  record(r2, pyAsyncLatency);
  sleep(0.05);
}

export function gatherTest() {
  const r1 = get("/predict/official/sample?mode=gather");
  check(r1, { "official gather 200": (r) => r.status === 200 });
  record(r1, officialGatherLatency);
  sleep(0.05);

  const r2 = get("/predict/py-async/sample?mode=gather");
  check(r2, { "py-async gather 200": (r) => r.status === 200 });
  record(r2, pyAsyncGatherLatency);
  sleep(0.05);
}

export function stressTest() {
  const r = get("/predict/py-async/sample");
  check(r, { "stress ok": (r) => r.status === 200 });
  record(r, pyAsyncStressLatency);
  sleep(0.05);
}
