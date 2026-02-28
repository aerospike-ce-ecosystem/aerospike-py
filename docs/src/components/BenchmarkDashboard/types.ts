// ── Benchmark Data Types ─────────────────────────────────────

export interface OpMetrics {
  avg_ms: number | null;
  p50_ms: number | null;
  p99_ms: number | null;
  ops_per_sec: number | null;
}

export type ClientSection = Record<string, OpMetrics>;

// ── Advanced Scenario Types ─────────────────────────────────

export interface DataSizeEntry {
  label: string;
  num_bins: number;
  value_size: number;
  put: Record<string, number | null>;
  get: Record<string, number | null>;
  official_put?: Record<string, number | null>;
  official_get?: Record<string, number | null>;
}

export interface DataSizeResult {
  count: number;
  rounds: number;
  has_official?: boolean;
  data: DataSizeEntry[];
}

export interface MemoryEntry {
  label: string;
  num_bins: number;
  value_size: number;
  put_peak_kb: number;
  get_peak_kb: number;
  batch_read_peak_kb: number;
  official_get_peak_kb?: number;
  official_batch_read_peak_kb?: number;
  c_get_peak_kb?: number;
  c_batch_read_peak_kb?: number;
}

export interface MemoryResult {
  count: number;
  has_c: boolean;
  has_official: boolean;
  data: MemoryEntry[];
}

export interface MixedEntry {
  label: string;
  read_ratio: number;
  throughput_ops_sec: number;
  read?: {
    count: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    avg_ms: number;
  };
  write?: {
    count: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    avg_ms: number;
  };
  official_throughput_ops_sec?: number;
  official_read?: {
    count: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    avg_ms: number;
  };
  official_write?: {
    count: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    avg_ms: number;
  };
}

export interface MixedResult {
  count: number;
  rounds: number;
  concurrency: number;
  has_official?: boolean;
  data: MixedEntry[];
}

// ── High Concurrency Scaling Types ─────────────────────────

export interface HighConcurrencyEntry {
  concurrency: number;
  aerospike_py: {
    ops_per_sec: number | null;
    per_op?: {
      p50_ms: number | null;
      p95_ms: number | null;
      p99_ms: number | null;
    };
  };
  official?: {
    ops_per_sec: number | null;
    per_op?: {
      p50_ms: number | null;
      p95_ms: number | null;
      p99_ms: number | null;
    };
  };
}

export interface HighConcurrencyResult {
  count: number;
  rounds: number;
  has_official: boolean;
  data: HighConcurrencyEntry[];
}

// ── Latency Simulation Types ────────────────────────────────

export interface LatencySimEntry {
  rtt_ms: number;
  concurrency: number;
  aerospike_py: {
    ops_per_sec: number | null;
    per_op?: {
      p50_ms: number | null;
      p99_ms: number | null;
    };
  };
  official?: {
    ops_per_sec: number | null;
    per_op?: {
      p50_ms: number | null;
      p99_ms: number | null;
    };
  };
}

export interface LatencySimResult {
  count: number;
  rounds: number;
  concurrency: number;
  has_official: boolean;
  simulation: boolean;
  data: LatencySimEntry[];
}

// ── Full Benchmark Data ─────────────────────────────────────

export interface EnvironmentConfig {
  platform: string;
  python_version: string;
  count: number;
  rounds: number;
  warmup: number;
  concurrency: number;
  batch_groups: number;
}

export interface FullBenchmarkData {
  timestamp: string;
  date: string;
  environment: EnvironmentConfig;
  aerospike_py_sync: ClientSection;
  official_sync: ClientSection | null;
  aerospike_py_async: ClientSection;
  official_async: ClientSection | null;
  data_size?: DataSizeResult;
  memory_profiling?: MemoryResult;
  mixed_workload?: MixedResult;
  high_concurrency_scaling?: HighConcurrencyResult;
  latency_sim?: LatencySimResult;
  numpy_batch?: NumpyBenchmarkData;
  takeaways: string[];
}

// ── NumPy Benchmark Types ───────────────────────────────────

export interface NumpyMetricsEntry {
  avg_ms: number | null;
  ops_per_sec: number | null;
  stdev_ms: number | null;
}

export interface RecordScalingEntry {
  record_count: number;
  batch_read_sync: NumpyMetricsEntry;
  batch_read_numpy_sync: NumpyMetricsEntry;
  batch_read_async: NumpyMetricsEntry;
  batch_read_numpy_async: NumpyMetricsEntry;
}

export interface BinScalingEntry {
  bin_count: number;
  batch_read_sync: NumpyMetricsEntry;
  batch_read_numpy_sync: NumpyMetricsEntry;
  batch_read_async: NumpyMetricsEntry;
  batch_read_numpy_async: NumpyMetricsEntry;
}

export interface PostProcessingEntry {
  stage: string;
  stage_label: string;
  batch_read_sync: NumpyMetricsEntry;
  batch_read_numpy_sync: NumpyMetricsEntry;
  batch_read_async: NumpyMetricsEntry;
  batch_read_numpy_async: NumpyMetricsEntry;
}

export interface NumpyMemoryEntry {
  record_count: number;
  dict_peak_kb: number;
  numpy_peak_kb: number;
  savings_pct: number;
}

export interface NumpyBenchmarkData {
  timestamp?: string;
  date?: string;
  report_type?: string;
  environment?: {
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
    data: NumpyMemoryEntry[];
  };
  takeaways: string[];
}

// ── Chart Color Mode ────────────────────────────────────────

export type ColorMode = 'light' | 'dark';

// ── Speedup Result ──────────────────────────────────────────

export interface SpeedupResult {
  text: string;
  className: string;
}
