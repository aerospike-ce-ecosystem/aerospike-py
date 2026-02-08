import React, {useEffect, useState} from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
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
  charts: Record<string, string>;
  takeaways: string[];
}

interface IndexData {
  reports: {date: string; file: string}[];
}

// ── Constants ───────────────────────────────────────────────

const OPERATIONS = ['put', 'get', 'batch_read', 'batch_write', 'scan'] as const;
const OP_LABELS: Record<string, string> = {
  put: 'PUT',
  get: 'GET',
  batch_read: 'BATCH_READ',
  batch_write: 'BATCH_WRITE',
  scan: 'SCAN',
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
    <table className={styles.table}>
      <thead>
        <tr>
          <th>항목</th>
          <th>값</th>
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
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>aerospike-py (Rust)</th>
          {hasC && <th>official aerospike (C)</th>}
          <th>aerospike-py async</th>
          {hasC && <th>Rust vs C</th>}
          {hasC && <th>Async vs C</th>}
        </tr>
      </thead>
      <tbody>
        {OPERATIONS.map((op) => {
          const rv = data.rust_sync[op]?.[metric] ?? null;
          const cv = hasC ? (data.c_sync![op]?.[metric] ?? null) : null;
          const av = data.rust_async[op]?.[metric] ?? null;
          const rustVsC = hasC ? calcSpeedup(rv, cv, latency) : null;
          const asyncVsC = hasC ? calcSpeedup(av, cv, latency) : null;
          return (
            <tr key={op}>
              <td>{OP_LABELS[op]}</td>
              <td className={styles.numCell}>{formatter(rv)}</td>
              {hasC && <td className={styles.numCell}>{formatter(cv)}</td>}
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
  );
}

function StabilityTable({data}: {data: BenchmarkData}) {
  const hasC = data.c_sync != null;
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>Rust stdev</th>
          {hasC && <th>C stdev</th>}
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
  );
}

function TailLatencyTable({data}: {data: BenchmarkData}) {
  const hasC = data.c_sync != null;
  const ops = OPERATIONS.filter((op) => data.rust_sync[op]?.p50_ms != null);
  if (ops.length === 0) return null;
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Operation</th>
          <th>Rust p50</th>
          <th>Rust p99</th>
          {hasC && <th>C p50</th>}
          {hasC && <th>C p99</th>}
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
  );
}

function ChartImg({src, alt}: {src: string; alt: string}) {
  const url = useBaseUrl(src);
  return <img className={styles.chart} src={url} alt={alt} />;
}

function ReportView({data}: {data: BenchmarkData}) {
  const hasTail = OPERATIONS.some((op) => data.rust_sync[op]?.p50_ms != null);

  return (
    <div>
      <h2>Environment</h2>
      <EnvironmentTable env={data.environment} />

      <h2>Latency Comparison</h2>
      {data.charts.latency && (
        <ChartImg src={data.charts.latency} alt="Latency Comparison" />
      )}
      <ComparisonTable data={data} metric="avg_ms" formatter={fmtMs} latency={true} />

      <h2>Throughput Comparison</h2>
      {data.charts.throughput && (
        <ChartImg src={data.charts.throughput} alt="Throughput Comparison" />
      )}
      <ComparisonTable data={data} metric="ops_per_sec" formatter={fmtOps} latency={false} />

      <h2>Stability (stdev)</h2>
      <StabilityTable data={data} />

      {hasTail && (
        <>
          <h2>Tail Latency (p50/p99)</h2>
          {data.charts.tail_latency && (
            <ChartImg src={data.charts.tail_latency} alt="Tail Latency" />
          )}
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

  // Load individual report when a tab is selected
  const loadReport = (date: string, file: string) => {
    if (reports[date]) return;
    fetch(`${baseUrl}${file}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load ${file}`);
        return res.json();
      })
      .then((data: BenchmarkData) =>
        setReports((prev) => ({...prev, [date]: data})),
      )
      .catch((err) => setError(err.message));
  };

  // Auto-load the first report
  useEffect(() => {
    if (index && index.reports.length > 0) {
      const first = index.reports[0];
      loadReport(first.date, first.file);
    }
  }, [index]);

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.errorBox}>
          <strong>벤치마크 데이터를 불러올 수 없습니다.</strong>
          <p><code>make run-benchmark-report</code>를 실행하여 벤치마크 데이터를 생성하세요.</p>
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
        <p>벤치마크 결과가 없습니다. <code>make run-benchmark-report</code>를 실행하세요.</p>
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
            {(() => {
              // Trigger load on render
              if (!reports[entry.date]) {
                loadReport(entry.date, entry.file);
                return <p>Loading {entry.date}...</p>;
              }
              return <ReportView data={reports[entry.date]} />;
            })()}
          </TabItem>
        ))}
      </Tabs>
    </div>
  );
}
