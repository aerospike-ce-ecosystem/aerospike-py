import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  LabelList,
} from 'recharts';

// ── Types ───────────────────────────────────────────────────

interface OpMetrics {
  avg_ms: number | null;
  p50_ms: number | null;
  p99_ms: number | null;
  ops_per_sec: number | null;
  stdev_ms: number | null;
}

type ClientSection = Record<string, OpMetrics>;

interface BenchmarkData {
  rust_sync: ClientSection;
  c_sync: ClientSection | null;
  rust_async: ClientSection;
  [key: string]: unknown;
}

type ColorMode = 'light' | 'dark';

interface ChartProps {
  data: BenchmarkData;
  colorMode: ColorMode;
}

// ── Constants ───────────────────────────────────────────────

const COLOR_SYNC = '#673ab7';
const COLOR_OFFICIAL = '#78909c';
const COLOR_ASYNC = '#4caf50';

const OPERATIONS = ['put', 'get', 'batch_read', 'batch_read_numpy', 'batch_write', 'scan'] as const;
const OP_LABELS: Record<string, string> = {
  put: 'PUT',
  get: 'GET',
  batch_read: 'BATCH_READ',
  batch_read_numpy: 'BATCH_READ_NUMPY',
  batch_write: 'BATCH_WRITE',
  scan: 'SCAN',
};

// batch_read_numpy has no official equivalent; compare against official batch_read
const CROSS_OP_BASELINE: Record<string, string> = {
  batch_read_numpy: 'batch_read',
};

function themeColors(colorMode: ColorMode) {
  const isDark = colorMode === 'dark';
  return {
    text: isDark ? '#e0e0e0' : '#333333',
    grid: isDark ? '#444444' : '#cccccc',
    tooltipBg: isDark ? '#1e1e1e' : '#ffffff',
    tooltipBorder: isDark ? '#555555' : '#cccccc',
  };
}

// ── Custom Tooltip ──────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
  colorMode,
  unit,
}: {
  active?: boolean;
  payload?: Array<{name: string; value: number; color: string}>;
  label?: string;
  colorMode: ColorMode;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  const theme = themeColors(colorMode);
  return (
    <div
      style={{
        background: theme.tooltipBg,
        border: `1px solid ${theme.tooltipBorder}`,
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 13,
      }}
    >
      <p style={{margin: 0, fontWeight: 600, color: theme.text}}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{margin: '4px 0 0', color: entry.color}}>
          {entry.name}: {unit === 'ms' ? `${entry.value.toFixed(3)}ms` : `${entry.value.toLocaleString()}/s`}
        </p>
      ))}
    </div>
  );
}

// ── Speedup Label ───────────────────────────────────────────

function speedupLabel(target: number, baseline: number, lowerIsBetter: boolean): string | null {
  if (!target || !baseline) return null;
  const pct = lowerIsBetter
    ? ((baseline - target) / baseline) * 100
    : ((target - baseline) / baseline) * 100;
  if (pct > 0) return `${pct.toFixed(0)}%↑`;
  if (pct < 0) return `${Math.abs(pct).toFixed(0)}%↓`;
  return null;
}

// ── LatencyChart ────────────────────────────────────────────

export function LatencyChart({data, colorMode}: ChartProps) {
  const hasC = data.c_sync != null;
  const theme = themeColors(colorMode);

  const chartData = OPERATIONS.map((op) => {
    const syncVal = data.rust_sync[op]?.avg_ms ?? 0;
    const asyncVal = data.rust_async[op]?.avg_ms ?? 0;
    const officialOp = CROSS_OP_BASELINE[op] ?? op;
    const officialVal = hasC ? (data.c_sync![officialOp]?.avg_ms ?? 0) : 0;

    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      Sync: syncVal,
      Async: asyncVal,
    };
    if (hasC) {
      entry.Official = officialVal;
      entry.syncLabel = speedupLabel(syncVal, officialVal, true);
      entry.asyncLabel = speedupLabel(asyncVal, officialVal, true);
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 30, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync" name="aerospike-py (SyncClient)" fill={COLOR_SYNC}>
            {hasC && <LabelList dataKey="syncLabel" position="top" fill={COLOR_SYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
          {hasC && (
            <Bar dataKey="Official" name="aerospike (official)" fill={COLOR_OFFICIAL} />
          )}
          <Bar dataKey="Async" name="aerospike-py (AsyncClient)" fill={COLOR_ASYNC}>
            {hasC && <LabelList dataKey="asyncLabel" position="top" fill={COLOR_ASYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── ThroughputChart ─────────────────────────────────────────

export function ThroughputChart({data, colorMode}: ChartProps) {
  const hasC = data.c_sync != null;
  const theme = themeColors(colorMode);

  const chartData = OPERATIONS.map((op) => {
    const syncVal = data.rust_sync[op]?.ops_per_sec ?? 0;
    const asyncVal = data.rust_async[op]?.ops_per_sec ?? 0;
    const officialOp = CROSS_OP_BASELINE[op] ?? op;
    const officialVal = hasC ? (data.c_sync![officialOp]?.ops_per_sec ?? 0) : 0;

    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      Sync: syncVal,
      Async: asyncVal,
    };
    if (hasC) {
      entry.Official = officialVal;
      entry.syncLabel = speedupLabel(syncVal, officialVal, false);
      entry.asyncLabel = speedupLabel(asyncVal, officialVal, false);
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 30, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Throughput (ops/sec)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ops" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync" name="aerospike-py (SyncClient)" fill={COLOR_SYNC}>
            {hasC && <LabelList dataKey="syncLabel" position="top" fill={COLOR_SYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
          {hasC && (
            <Bar dataKey="Official" name="aerospike (official)" fill={COLOR_OFFICIAL} />
          )}
          <Bar dataKey="Async" name="aerospike-py (AsyncClient)" fill={COLOR_ASYNC}>
            {hasC && <LabelList dataKey="asyncLabel" position="top" fill={COLOR_ASYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── TailLatencyChart ────────────────────────────────────────

export function TailLatencyChart({data, colorMode}: ChartProps) {
  const hasC = data.c_sync != null;
  const theme = themeColors(colorMode);

  const ops = OPERATIONS.filter((op) => data.rust_sync[op]?.p50_ms != null);
  if (ops.length === 0) return null;

  const chartData = ops.map((op) => {
    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      'Sync p50': data.rust_sync[op]?.p50_ms ?? 0,
      'Sync p99': data.rust_sync[op]?.p99_ms ?? 0,
    };
    if (hasC) {
      entry['Official p50'] = data.c_sync![op]?.p50_ms ?? 0;
      entry['Official p99'] = data.c_sync![op]?.p99_ms ?? 0;
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync p50" fill={COLOR_SYNC} fillOpacity={0.6} />
          <Bar dataKey="Sync p99" fill={COLOR_SYNC} fillOpacity={1.0} />
          {hasC && <Bar dataKey="Official p50" fill={COLOR_OFFICIAL} fillOpacity={0.6} />}
          {hasC && <Bar dataKey="Official p99" fill={COLOR_OFFICIAL} fillOpacity={1.0} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
