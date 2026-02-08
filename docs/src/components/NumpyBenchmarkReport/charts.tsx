import React from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

// ── Types ───────────────────────────────────────────────────

interface MetricsEntry {
  avg_ms: number | null;
  ops_per_sec: number | null;
  stdev_ms: number | null;
}

interface RecordScalingEntry {
  record_count: number;
  batch_read_sync: MetricsEntry;
  batch_read_numpy_sync: MetricsEntry;
  batch_read_async: MetricsEntry;
  batch_read_numpy_async: MetricsEntry;
}

interface BinScalingEntry {
  bin_count: number;
  batch_read_sync: MetricsEntry;
  batch_read_numpy_sync: MetricsEntry;
  batch_read_async: MetricsEntry;
  batch_read_numpy_async: MetricsEntry;
}

interface PostProcessingEntry {
  stage: string;
  stage_label: string;
  batch_read_sync: MetricsEntry;
  batch_read_numpy_sync: MetricsEntry;
  batch_read_async: MetricsEntry;
  batch_read_numpy_async: MetricsEntry;
}

interface MemoryEntry {
  record_count: number;
  dict_peak_kb: number;
  numpy_peak_kb: number;
  savings_pct: number;
}

export interface NumpyBenchmarkData {
  timestamp: string;
  date: string;
  report_type: string;
  environment: {
    platform: string;
    python_version: string;
    rounds: number;
    warmup: number;
    concurrency: number;
    batch_groups: number;
  };
  record_scaling?: {
    fixed_bins: number;
    data: RecordScalingEntry[];
  };
  bin_scaling?: {
    fixed_records: number;
    data: BinScalingEntry[];
  };
  post_processing?: {
    record_count: number;
    bin_count: number;
    data: PostProcessingEntry[];
  };
  memory?: {
    bin_count: number;
    data: MemoryEntry[];
  };
  takeaways: string[];
}

type ColorMode = 'light' | 'dark';

// ── Constants ───────────────────────────────────────────────

const COLOR_DICT_SYNC = '#673ab7';   // purple
const COLOR_NUMPY_SYNC = '#e91e63';  // pink
const COLOR_DICT_ASYNC = '#4caf50';  // green
const COLOR_NUMPY_ASYNC = '#2196f3'; // blue

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
          {entry.name}:{' '}
          {unit === 'ms'
            ? `${entry.value.toFixed(3)}ms`
            : unit === 'kb'
              ? `${entry.value.toLocaleString()} KB`
              : `${entry.value.toLocaleString()}/s`}
        </p>
      ))}
    </div>
  );
}

// ── Record Scaling Chart ────────────────────────────────────

export function RecordScalingChart({
  data,
  colorMode,
}: {
  data: NumpyBenchmarkData;
  colorMode: ColorMode;
}) {
  if (!data.record_scaling) return null;
  const theme = themeColors(colorMode);

  const chartData = data.record_scaling.data.map((d) => ({
    records: d.record_count.toLocaleString(),
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="records" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="batch_read (Sync)" stroke={COLOR_DICT_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Sync)" stroke={COLOR_NUMPY_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="batch_read (Async)" stroke={COLOR_DICT_ASYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Async)" stroke={COLOR_NUMPY_ASYNC} strokeWidth={2} dot={{r: 4}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Bin Scaling Chart ───────────────────────────────────────

export function BinScalingChart({
  data,
  colorMode,
}: {
  data: NumpyBenchmarkData;
  colorMode: ColorMode;
}) {
  if (!data.bin_scaling) return null;
  const theme = themeColors(colorMode);

  const chartData = data.bin_scaling.data.map((d) => ({
    bins: d.bin_count.toString(),
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="bins" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="batch_read (Sync)" stroke={COLOR_DICT_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Sync)" stroke={COLOR_NUMPY_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="batch_read (Async)" stroke={COLOR_DICT_ASYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Async)" stroke={COLOR_NUMPY_ASYNC} strokeWidth={2} dot={{r: 4}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Post-Processing Chart ───────────────────────────────────

export function PostProcessingChart({
  data,
  colorMode,
}: {
  data: NumpyBenchmarkData;
  colorMode: ColorMode;
}) {
  if (!data.post_processing) return null;
  const theme = themeColors(colorMode);

  const chartData = data.post_processing.data.map((d) => ({
    stage: d.stage_label,
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="stage" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="batch_read (Sync)" fill={COLOR_DICT_SYNC} />
          <Bar dataKey="numpy (Sync)" fill={COLOR_NUMPY_SYNC} />
          <Bar dataKey="batch_read (Async)" fill={COLOR_DICT_ASYNC} />
          <Bar dataKey="numpy (Async)" fill={COLOR_NUMPY_ASYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Memory Chart ────────────────────────────────────────────

export function MemoryChart({
  data,
  colorMode,
}: {
  data: NumpyBenchmarkData;
  colorMode: ColorMode;
}) {
  if (!data.memory) return null;
  const theme = themeColors(colorMode);

  const chartData = data.memory.data.map((d) => ({
    records: d.record_count.toLocaleString(),
    'dict (KB)': d.dict_peak_kb,
    'numpy (KB)': d.numpy_peak_kb,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="records" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Peak Memory (KB)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="kb" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="dict (KB)" fill={COLOR_DICT_SYNC} />
          <Bar dataKey="numpy (KB)" fill={COLOR_NUMPY_SYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
