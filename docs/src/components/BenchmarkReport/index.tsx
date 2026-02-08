import React, {useEffect, useState} from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import BrowserOnly from '@docusaurus/BrowserOnly';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './BenchmarkReport.module.css';

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
  timestamp: string;
  date: string;
  environment: {
    platform: string;
    python_version: string;
    count: number;
    rounds: number;
    warmup: number;
    concurrency: number;
    batch_groups: number;
  };
  rust_sync: ClientSection;
  c_sync: ClientSection | null;
  rust_async: ClientSection;
  charts?: Record<string, string>;
  takeaways: string[];
}

interface IndexData {
  reports: {date: string; file: string}[];
}

// ── Constants ───────────────────────────────────────────────

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

// ── Helpers ─────────────────────────────────────────────────

function fmtMs(val: number | null): string {
  if (val == null) return '-';
  return `${val.toFixed(3)}ms`;
}

function fmtOps(val: number | null): string {
  if (val == null) return '-';
  return `${val.toLocaleString('en-US', {maximumFractionDigits: 0})}/s`;
}

interface SpeedupResult {
  text: string;
  className: string;
}

function calcSpeedup(
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
      className: styles.faster,
    };
  }
  const inv = 1 / ratio;
  const pct = (inv - 1) * 100;
  return {
    text: `${inv.toFixed(1)}x slower (${pct.toFixed(0)}%)`,
    className: styles.slower,
  };
}

// ── Sub-components ──────────────────────────────────────────

function EnvironmentTable({env}: {env: BenchmarkData['environment']}) {
  return (
    <div className={styles.tableWrap}>
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Item</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Platform</td><td>{env.platform}</td></tr>
        <tr><td>Python</td><td>{env.python_version}</td></tr>
        <tr><td>Operations/round</td><td>{env.count.toLocaleString()}</td></tr>
        <tr><td>Rounds</td><td>{env.rounds}</td></tr>
        <tr><td>Warmup</td><td>{env.warmup}</td></tr>
        <tr><td>Async concurrency</td><td>{env.concurrency}</td></tr>
        <tr><td>Batch groups</td><td>{env.batch_groups}</td></tr>
      </tbody>
    </table>
    </div>
  );
}

function ComparisonTable({
  data,
  metric,
  formatter,
  latency,
}: {
  data: BenchmarkData;
  metric: 'avg_ms' | 'ops_per_sec';
  formatter: (v: number | null) => string;
  latency: boolean;
}) {
  const hasC = data.c_sync != null;
  return (
    <div className={styles.tableWrap}>
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>aerospike-py (SyncClient)</th>
          {hasC && <th>aerospike (official)</th>}
          <th>aerospike-py (AsyncClient)</th>
          {hasC && <th>Sync vs Official</th>}
          {hasC && <th>Async vs Official</th>}
        </tr>
      </thead>
      <tbody>
        {OPERATIONS.map((op) => {
          const rv = data.rust_sync[op]?.[metric] ?? null;
          const av = data.rust_async[op]?.[metric] ?? null;

          // cross-op baseline: use another operation's official value
          const officialOp = CROSS_OP_BASELINE[op] ?? op;
          const isCrossOp = officialOp !== op;
          const cv = hasC ? (data.c_sync![officialOp]?.[metric] ?? null) : null;

          const rustVsC = hasC ? calcSpeedup(rv, cv, latency) : null;
          const asyncVsC = hasC ? calcSpeedup(av, cv, latency) : null;
          return (
            <tr key={op}>
              <td>{OP_LABELS[op]}{isCrossOp ? ' *' : ''}</td>
              <td className={styles.numCell}>{formatter(rv)}</td>
              {hasC && <td className={styles.numCell}>{isCrossOp ? `${formatter(cv)} †` : formatter(cv)}</td>}
              <td className={styles.numCell}>{formatter(av)}</td>
              {hasC && (
                <td className={`${styles.numCell} ${rustVsC!.className}`}>
                  {rustVsC!.text}
                </td>
              )}
              {hasC && (
                <td className={`${styles.numCell} ${asyncVsC!.className}`}>
                  {asyncVsC!.text}
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
    {hasC && (
      <p style={{fontSize: '0.85em', color: 'var(--ifm-color-emphasis-600)', marginTop: 4}}>
        * BATCH_READ_NUMPY is compared against Official's BATCH_READ († same data, different return format: numpy structured array vs Python dict)
      </p>
    )}
    </div>
  );
}

function StabilityTable({data}: {data: BenchmarkData}) {
  const hasC = data.c_sync != null;
  return (
    <div className={styles.tableWrap}>
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>Sync stdev</th>
          {hasC && <th>Official stdev</th>}
          <th>Async stdev</th>
        </tr>
      </thead>
      <tbody>
        {OPERATIONS.map((op) => (
          <tr key={op}>
            <td>{OP_LABELS[op]}</td>
            <td className={styles.numCell}>{fmtMs(data.rust_sync[op]?.stdev_ms ?? null)}</td>
            {hasC && (
              <td className={styles.numCell}>{fmtMs(data.c_sync![op]?.stdev_ms ?? null)}</td>
            )}
            <td className={styles.numCell}>{fmtMs(data.rust_async[op]?.stdev_ms ?? null)}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function TailLatencyTable({data}: {data: BenchmarkData}) {
  const hasC = data.c_sync != null;
  const ops = OPERATIONS.filter((op) => data.rust_sync[op]?.p50_ms != null);
  if (ops.length === 0) return null;
  return (
    <div className={styles.tableWrap}>
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>Sync p50</th>
          <th>Sync p99</th>
          {hasC && <th>Official p50</th>}
          {hasC && <th>Official p99</th>}
        </tr>
      </thead>
      <tbody>
        {ops.map((op) => (
          <tr key={op}>
            <td>{OP_LABELS[op]}</td>
            <td className={styles.numCell}>{fmtMs(data.rust_sync[op]?.p50_ms ?? null)}</td>
            <td className={styles.numCell}>{fmtMs(data.rust_sync[op]?.p99_ms ?? null)}</td>
            {hasC && (
              <td className={styles.numCell}>{fmtMs(data.c_sync![op]?.p50_ms ?? null)}</td>
            )}
            {hasC && (
              <td className={styles.numCell}>{fmtMs(data.c_sync![op]?.p99_ms ?? null)}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function ReportView({data}: {data: BenchmarkData}) {
  const hasTail = OPERATIONS.some((op) => data.rust_sync[op]?.p50_ms != null);
  const {colorMode} = useColorMode();

  return (
    <div>
      <h2>Environment</h2>
      <EnvironmentTable env={data.environment} />

      <h2>Latency Comparison</h2>
      <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
        {() => {
          const {LatencyChart} = require('./charts');
          return <LatencyChart data={data} colorMode={colorMode} />;
        }}
      </BrowserOnly>
      <ComparisonTable data={data} metric="avg_ms" formatter={fmtMs} latency={true} />

      <h2>Throughput Comparison</h2>
      <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
        {() => {
          const {ThroughputChart} = require('./charts');
          return <ThroughputChart data={data} colorMode={colorMode} />;
        }}
      </BrowserOnly>
      <ComparisonTable data={data} metric="ops_per_sec" formatter={fmtOps} latency={false} />

      <h2>Stability (stdev)</h2>
      <StabilityTable data={data} />

      {hasTail && (
        <>
          <h2>Tail Latency (p50/p99)</h2>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {TailLatencyChart} = require('./charts');
              return <TailLatencyChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <TailLatencyTable data={data} />
        </>
      )}

      <h2>Key Takeaways</h2>
      <ul>
        {data.takeaways.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

// ── Lazy-loading wrapper ────────────────────────────────────

function LazyReportView({
  date,
  file,
  baseUrl,
  reports,
  onLoad,
  onError,
}: {
  date: string;
  file: string;
  baseUrl: string;
  reports: Record<string, BenchmarkData>;
  onLoad: (date: string, data: BenchmarkData) => void;
  onError: (msg: string) => void;
}) {
  useEffect(() => {
    if (reports[date]) return;
    fetch(`${baseUrl}${file}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load ${file}`);
        return res.json();
      })
      .then((data: BenchmarkData) => onLoad(date, data))
      .catch((err) => onError(err.message));
  }, [date, file, baseUrl, reports, onLoad, onError]);

  if (!reports[date]) {
    return <p>Loading {date}...</p>;
  }
  return <ReportView data={reports[date]} />;
}

// ── Main Component ──────────────────────────────────────────

export default function BenchmarkReport(): React.ReactElement {
  const [index, setIndex] = useState<IndexData | null>(null);
  const [reports, setReports] = useState<Record<string, BenchmarkData>>({});
  const [error, setError] = useState<string | null>(null);

  const baseUrl = useBaseUrl('/benchmark/results/');

  useEffect(() => {
    fetch(`${baseUrl}index.json`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load index.json (${res.status})`);
        return res.json();
      })
      .then((data: IndexData) => setIndex(data))
      .catch((err) => setError(err.message));
  }, [baseUrl]);

  const handleLoad = React.useCallback(
    (date: string, data: BenchmarkData) => {
      setReports((prev) => ({...prev, [date]: data}));
    },
    [],
  );

  const handleError = React.useCallback(
    (msg: string) => setError(msg),
    [],
  );

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.errorBox}>
          <strong>Failed to load benchmark data.</strong>
          <p>Run <code>make run-benchmark-report</code> to generate benchmark data.</p>
          <details><summary>Error details</summary><pre>{error}</pre></details>
        </div>
      </div>
    );
  }

  if (!index) {
    return <div className={styles.container}>Loading benchmark data...</div>;
  }

  if (index.reports.length === 0) {
    return (
      <div className={styles.container}>
        <p>No benchmark results available. Run <code>make run-benchmark-report</code> to generate results.</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Tabs>
        {index.reports.map((entry) => (
          <TabItem
            key={entry.date}
            value={entry.date}
            label={entry.date}
            default={entry.date === index.reports[0].date}
          >
            <LazyReportView
              date={entry.date}
              file={entry.file}
              baseUrl={baseUrl}
              reports={reports}
              onLoad={handleLoad}
              onError={handleError}
            />
          </TabItem>
        ))}
      </Tabs>
    </div>
  );
}
