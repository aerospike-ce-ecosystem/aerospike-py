import React, {useEffect, useState} from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import BrowserOnly from '@docusaurus/BrowserOnly';
import {useColorMode} from '@docusaurus/theme-common';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './NumpyBenchmarkReport.module.css';
import type {NumpyBenchmarkData} from './charts';

// ── Types ───────────────────────────────────────────────────

interface IndexData {
  reports: {date: string; file: string}[];
}

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
  numpyMs: number | null,
  dictMs: number | null,
): SpeedupResult {
  if (numpyMs == null || dictMs == null || numpyMs <= 0 || dictMs <= 0) {
    return {text: '-', className: ''};
  }
  const ratio = dictMs / numpyMs;
  if (ratio >= 1.0) {
    return {
      text: `${ratio.toFixed(1)}x faster`,
      className: styles.faster,
    };
  }
  const inv = 1 / ratio;
  return {
    text: `${inv.toFixed(1)}x slower`,
    className: styles.slower,
  };
}

// ── Sub-components ──────────────────────────────────────────

function EnvironmentTable({env}: {env: NumpyBenchmarkData['environment']}) {
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
          <tr><td>Rounds</td><td>{env.rounds}</td></tr>
          <tr><td>Warmup</td><td>{env.warmup}</td></tr>
          <tr><td>Async concurrency</td><td>{env.concurrency}</td></tr>
          <tr><td>Batch groups</td><td>{env.batch_groups}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

function ScalingTable({
  data,
  xLabel,
  xKey,
}: {
  data: NumpyBenchmarkData;
  xLabel: string;
  xKey: 'record_scaling' | 'bin_scaling';
}) {
  const section = data[xKey];
  if (!section) return null;
  const valueKey = xKey === 'record_scaling' ? 'record_count' : 'bin_count';

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{xLabel}</th>
            <th>batch_read (Sync)</th>
            <th>numpy (Sync)</th>
            <th>batch_read (Async)</th>
            <th>numpy (Async)</th>
            <th>Speedup (Sync)</th>
            <th>Speedup (Async)</th>
          </tr>
        </thead>
        <tbody>
          {section.data.map((entry: any) => {
            const brSync = entry.batch_read_sync?.avg_ms ?? null;
            const npSync = entry.batch_read_numpy_sync?.avg_ms ?? null;
            const brAsync = entry.batch_read_async?.avg_ms ?? null;
            const npAsync = entry.batch_read_numpy_async?.avg_ms ?? null;
            const spSync = calcSpeedup(npSync, brSync);
            const spAsync = calcSpeedup(npAsync, brAsync);

            return (
              <tr key={entry[valueKey]}>
                <td>{entry[valueKey].toLocaleString()}</td>
                <td className={styles.numCell}>{fmtMs(brSync)}</td>
                <td className={styles.numCell}>{fmtMs(npSync)}</td>
                <td className={styles.numCell}>{fmtMs(brAsync)}</td>
                <td className={styles.numCell}>{fmtMs(npAsync)}</td>
                <td className={`${styles.numCell} ${spSync.className}`}>{spSync.text}</td>
                <td className={`${styles.numCell} ${spAsync.className}`}>{spAsync.text}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PostProcessingTable({data}: {data: NumpyBenchmarkData}) {
  if (!data.post_processing) return null;

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Stage</th>
            <th>batch_read (Sync)</th>
            <th>numpy (Sync)</th>
            <th>batch_read (Async)</th>
            <th>numpy (Async)</th>
            <th>Speedup (Sync)</th>
            <th>Speedup (Async)</th>
          </tr>
        </thead>
        <tbody>
          {data.post_processing.data.map((entry) => {
            const brSync = entry.batch_read_sync?.avg_ms ?? null;
            const npSync = entry.batch_read_numpy_sync?.avg_ms ?? null;
            const brAsync = entry.batch_read_async?.avg_ms ?? null;
            const npAsync = entry.batch_read_numpy_async?.avg_ms ?? null;
            const spSync = calcSpeedup(npSync, brSync);
            const spAsync = calcSpeedup(npAsync, brAsync);

            return (
              <tr key={entry.stage}>
                <td>{entry.stage_label}</td>
                <td className={styles.numCell}>{fmtMs(brSync)}</td>
                <td className={styles.numCell}>{fmtMs(npSync)}</td>
                <td className={styles.numCell}>{fmtMs(brAsync)}</td>
                <td className={styles.numCell}>{fmtMs(npAsync)}</td>
                <td className={`${styles.numCell} ${spSync.className}`}>{spSync.text}</td>
                <td className={`${styles.numCell} ${spAsync.className}`}>{spAsync.text}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MemoryTable({data}: {data: NumpyBenchmarkData}) {
  if (!data.memory) return null;

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Records</th>
            <th>dict peak (KB)</th>
            <th>numpy peak (KB)</th>
            <th>Savings</th>
          </tr>
        </thead>
        <tbody>
          {data.memory.data.map((entry) => {
            const savingsClass = entry.savings_pct > 0 ? styles.faster : entry.savings_pct < 0 ? styles.slower : '';
            return (
              <tr key={entry.record_count}>
                <td>{entry.record_count.toLocaleString()}</td>
                <td className={styles.numCell}>{entry.dict_peak_kb.toLocaleString()} KB</td>
                <td className={styles.numCell}>{entry.numpy_peak_kb.toLocaleString()} KB</td>
                <td className={`${styles.numCell} ${savingsClass}`}>{entry.savings_pct.toFixed(1)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Report View ─────────────────────────────────────────────

function ReportView({data}: {data: NumpyBenchmarkData}) {
  const {colorMode} = useColorMode();

  return (
    <div>
      <h2>Environment</h2>
      <EnvironmentTable env={data.environment} />

      {data.record_scaling && (
        <>
          <h2>Record Count Scaling</h2>
          <p>Fixed bins: {data.record_scaling.fixed_bins}. Measures how numpy advantage scales with record count.</p>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {RecordScalingChart} = require('./charts');
              return <RecordScalingChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <ScalingTable data={data} xLabel="Records" xKey="record_scaling" />
        </>
      )}

      {data.bin_scaling && (
        <>
          <h2>Bin Count Scaling</h2>
          <p>Fixed records: {data.bin_scaling.fixed_records}. Measures how bin (column) count affects numpy performance.</p>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {BinScalingChart} = require('./charts');
              return <BinScalingChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <ScalingTable data={data} xLabel="Bins" xKey="bin_scaling" />
        </>
      )}

      {data.post_processing && (
        <>
          <h2>Post-Processing Comparison</h2>
          <p>
            Records: {data.post_processing.record_count}, Bins: {data.post_processing.bin_count}.
            Compares dict vs numpy at each data processing stage.
          </p>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {PostProcessingChart} = require('./charts');
              return <PostProcessingChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <PostProcessingTable data={data} />
        </>
      )}

      {data.memory && (
        <>
          <h2>Memory Usage</h2>
          <p>Bins: {data.memory.bin_count}. Peak memory measured via tracemalloc (Sync client only).</p>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {MemoryChart} = require('./charts');
              return <MemoryChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <MemoryTable data={data} />
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
  reports: Record<string, NumpyBenchmarkData>;
  onLoad: (date: string, data: NumpyBenchmarkData) => void;
  onError: (msg: string) => void;
}) {
  useEffect(() => {
    if (reports[date]) return;
    fetch(`${baseUrl}${file}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load ${file}`);
        return res.json();
      })
      .then((data: NumpyBenchmarkData) => onLoad(date, data))
      .catch((err) => onError(err.message));
  }, [date, file, baseUrl, reports, onLoad, onError]);

  if (!reports[date]) {
    return <p>Loading {date}...</p>;
  }
  return <ReportView data={reports[date]} />;
}

// ── Main Component ──────────────────────────────────────────

export default function NumpyBenchmarkReport(): React.ReactElement {
  const [index, setIndex] = useState<IndexData | null>(null);
  const [reports, setReports] = useState<Record<string, NumpyBenchmarkData>>({});
  const [error, setError] = useState<string | null>(null);

  const baseUrl = useBaseUrl('/benchmark/numpy-results/');

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
    (date: string, data: NumpyBenchmarkData) => {
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
          <strong>Failed to load numpy benchmark data.</strong>
          <p>Run <code>make run-numpy-benchmark-report</code> to generate benchmark data.</p>
          <details><summary>Error details</summary><pre>{error}</pre></details>
        </div>
      </div>
    );
  }

  if (!index) {
    return <div className={styles.container}>Loading numpy benchmark data...</div>;
  }

  if (index.reports.length === 0) {
    return (
      <div className={styles.container}>
        <p>No numpy benchmark results available. Run <code>make run-numpy-benchmark-report</code> to generate results.</p>
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
