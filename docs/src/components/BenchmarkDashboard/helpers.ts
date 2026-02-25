import type {SpeedupResult, FullBenchmarkData} from './types';
import {OPERATIONS, CROSS_OP_BASELINE} from './constants';

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

  // Find best speedup (async vs official)
  if (data.c_sync) {
    let bestSpeedup = 0;
    let bestOp = '';

    for (const op of OPERATIONS) {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      const asyncVal = data.rust_async[op]?.avg_ms;
      const officialVal = data.c_sync[officialOp]?.avg_ms;
      if (asyncVal && officialVal && asyncVal > 0) {
        const ratio = officialVal / asyncVal;
        if (ratio > bestSpeedup) {
          bestSpeedup = ratio;
          bestOp = op.toUpperCase();
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
    const asyncOps = data.rust_async[op]?.ops_per_sec;
    const syncOps = data.rust_sync[op]?.ops_per_sec;
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
  const totalOps = Object.keys(data.rust_sync).length + Object.keys(data.rust_async).length;
  metrics.push({
    value: `${totalOps}`,
    label: 'BENCHMARKED OPS',
    color: 'warning',
  });

  return metrics;
}
