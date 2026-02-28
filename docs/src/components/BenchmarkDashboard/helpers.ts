import type {SpeedupResult, FullBenchmarkData, ClientSection, OpMetrics} from './types';
import {OPERATIONS, CROSS_OP_BASELINE} from './constants';

// ── Data Access Helpers ─────────────────────────────────────

export function hasOfficialData(data: FullBenchmarkData): boolean {
  return data.official_sync != null || data.official_async != null;
}

type NumericOpField = {
  [K in keyof OpMetrics]: OpMetrics[K] extends number | null | undefined ? K : never;
}[keyof OpMetrics];

export function getMetric(
  section: ClientSection | null | undefined,
  op: string,
  field: NumericOpField,
): number | null {
  return (section?.[op]?.[field] as number | null | undefined) ?? null;
}

export function getOfficialMetric(
  data: FullBenchmarkData, op: string, metric: NumericOpField,
): { sync: number | null; async_: number | null; baseline: number | null } {
  const officialOp = CROSS_OP_BASELINE[op] ?? op;
  const s = (data.official_sync?.[officialOp]?.[metric] as number | null | undefined) ?? null;
  const a = (data.official_async?.[officialOp]?.[metric] as number | null | undefined) ?? null;
  return { sync: s, async_: a, baseline: s ?? a };
}

// ── Formatters ──────────────────────────────────────────────

export function fmtMs(val: number | null | undefined): string {
  if (val == null) return '-';
  return `${val.toFixed(3)}ms`;
}

export function fmtOps(val: number | null | undefined): string {
  if (val == null) return '-';
  return `${val.toLocaleString('en-US', {maximumFractionDigits: 0})}/s`;
}

export function fmtKb(val: number | null | undefined): string {
  if (val == null) return '-';
  if (val >= 1024) return `${(val / 1024).toFixed(1)} MB`;
  return `${val.toFixed(1)} KB`;
}

export function shortLabel(label: string): string {
  return label.split(' (')[0];
}

export function fmtPct(val: number | null | undefined): string {
  if (val == null) return '-';
  return `${val.toFixed(1)}%`;
}

// ── Speedup Calculators ─────────────────────────────────────

export function calcSpeedup(
  target: number | null,
  baseline: number | null,
  latency: boolean,
): SpeedupResult {
  if (target == null || baseline == null || target <= 0 || baseline <= 0) {
    return {text: '-', className: ''};
  }
  const ratio = latency ? baseline / target : target / baseline;
  if (ratio >= 1.0) {
    const pct = (ratio - 1) * 100;
    return {
      text: `${ratio.toFixed(1)}x faster (${pct.toFixed(0)}%)`,
      className: 'faster',
    };
  }
  const inv = 1 / ratio;
  const pct = (inv - 1) * 100;
  return {
    text: `${inv.toFixed(1)}x slower (${pct.toFixed(0)}%)`,
    className: 'slower',
  };
}

export function calcNumpySpeedup(
  numpyMs: number | null,
  dictMs: number | null,
): SpeedupResult {
  if (numpyMs == null || dictMs == null || numpyMs <= 0 || dictMs <= 0) {
    return {text: '-', className: ''};
  }
  const ratio = dictMs / numpyMs;
  if (ratio >= 1.0) {
    return {text: `${ratio.toFixed(1)}x faster`, className: 'faster'};
  }
  const inv = 1 / ratio;
  return {text: `${inv.toFixed(1)}x slower`, className: 'slower'};
}

// ── Hero Metrics Extraction ─────────────────────────────────

export interface HeroMetric {
  value: string;
  label: string;
  color: 'primary' | 'success' | 'warning';
}

export function extractHeroMetrics(data: FullBenchmarkData): HeroMetric[] {
  const metrics: HeroMetric[] = [];
  const hasOfficial = hasOfficialData(data);

  // Find best speedup (aerospike-py async vs official)
  if (hasOfficial) {
    let bestSpeedup = 0;
    let bestOp = '';
    // Compare against official_sync and official_async
    const officialSections = [data.official_sync, data.official_async].filter(Boolean) as ClientSection[];

    for (const op of OPERATIONS) {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      const asyncVal = data.aerospike_py_async[op]?.avg_ms;
      for (const officialSection of officialSections) {
        const officialVal = officialSection[officialOp]?.avg_ms;
        if (asyncVal && officialVal && asyncVal > 0) {
          const ratio = officialVal / asyncVal;
          if (ratio > bestSpeedup) {
            bestSpeedup = ratio;
            bestOp = op.toUpperCase();
          }
        }
      }
    }

    if (bestSpeedup > 1.0) {
      metrics.push({
        value: `${bestSpeedup.toFixed(1)}x`,
        label: `FASTER - AsyncClient ${bestOp}`,
        color: 'primary',
      });
    }
  }

  // Async vs Sync best throughput ratio
  let bestThroughputRatio = 0;
  let bestThroughputOp = '';
  for (const op of OPERATIONS) {
    const asyncOps = data.aerospike_py_async[op]?.ops_per_sec;
    const syncOps = data.aerospike_py_sync[op]?.ops_per_sec;
    if (asyncOps && syncOps && syncOps > 0) {
      const ratio = asyncOps / syncOps;
      if (ratio > bestThroughputRatio) {
        bestThroughputRatio = ratio;
        bestThroughputOp = op.toUpperCase();
      }
    }
  }
  if (bestThroughputRatio > 1.0) {
    metrics.push({
      value: `${bestThroughputRatio.toFixed(1)}x`,
      label: `THROUGHPUT - Async ${bestThroughputOp}`,
      color: 'success',
    });
  }

  // Operations count
  const totalOps = Object.keys(data.aerospike_py_sync).length + Object.keys(data.aerospike_py_async).length;
  metrics.push({
    value: `${totalOps}`,
    label: 'BENCHMARKED OPS',
    color: 'warning',
  });

  return metrics;
}
