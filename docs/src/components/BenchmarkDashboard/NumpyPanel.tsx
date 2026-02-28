import React from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import CollapsibleSection from './ui/CollapsibleSection';
import {LazyChart} from './ui/LazyChart';
import MetricCard from './MetricCard';
import {fmtMs, fmtPct, calcNumpySpeedup} from './helpers';
import {DataTable} from './ui/DataTable';
import tableStyles from './styles/Tables.module.css';
import cardStyles from './styles/Cards.module.css';
import heroBannerStyles from './styles/HeroBanner.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import type {NumpyBenchmarkData, ColorMode} from './types';

interface Props {
  numpyData: NumpyBenchmarkData | null;
  colorMode: ColorMode;
}

export default function NumpyPanel({numpyData, colorMode}: Props) {
  if (!numpyData) {
    return (
      <div style={{padding: '2rem', textAlign: 'center', color: 'var(--ifm-color-emphasis-600)'}}>
        No NumPy benchmark results available.
        <br />Run <code>make run-benchmark-report BENCH_SCENARIO=all</code> to generate results.
      </div>
    );
  }

  const data = numpyData;
  const summaryMetrics = extractNumpySummary(data);

  return (
    <div>
      {/* Summary Cards */}
      <div className={heroBannerStyles.metricsGrid} style={{marginBottom: '1.5rem'}}>
        {summaryMetrics.map((m, i) => (
          <MetricCard key={i} value={m.value} label={m.label} color={m.color} />
        ))}
      </div>

      {/* Inner Tabs */}
      <div className={dashStyles.innerTabs}>
        <Tabs groupId="numpy">
          {data.record_scaling && (
            <TabItem value="record" label="Record Scaling">
              <h4>Record Count Scaling</h4>
              <p>Fixed bins: {data.record_scaling.fixed_bins}. Measures how numpy advantage scales with record count.</p>
              <LazyChart render={() => {
                const {RecordScalingChart} = require('./charts/NumpyCharts');
                return <RecordScalingChart data={data} colorMode={colorMode} />;
              }} />
              <CollapsibleSection title="Record Scaling Detail Table">
                <ScalingTable data={data} xLabel="Records" xKey="record_scaling" />
              </CollapsibleSection>
            </TabItem>
          )}

          {data.bin_scaling && (
            <TabItem value="bin" label="Bin Scaling">
              <h4>Bin Count Scaling</h4>
              <p>Fixed records: {data.bin_scaling.fixed_records}. Measures how bin (column) count affects numpy performance.</p>
              <LazyChart render={() => {
                const {BinScalingChart} = require('./charts/NumpyCharts');
                return <BinScalingChart data={data} colorMode={colorMode} />;
              }} />
              <CollapsibleSection title="Bin Scaling Detail Table">
                <ScalingTable data={data} xLabel="Bins" xKey="bin_scaling" />
              </CollapsibleSection>
            </TabItem>
          )}

          {data.post_processing && (
            <TabItem value="postproc" label="Post-Processing">
              <h4>Post-Processing Comparison</h4>
              <p>
                Records: {data.post_processing.record_count}, Bins: {data.post_processing.bin_count}.
                Compares dict vs numpy at each data processing stage.
              </p>
              <LazyChart render={() => {
                const {PostProcessingChart} = require('./charts/NumpyCharts');
                return <PostProcessingChart data={data} colorMode={colorMode} />;
              }} />
              <CollapsibleSection title="Post-Processing Detail Table">
                <PostProcessingTable data={data} />
              </CollapsibleSection>
            </TabItem>
          )}

          {data.memory && (
            <TabItem value="npmemory" label="Memory">
              <h4>Memory Usage</h4>
              <p>Bins: {data.memory.bin_count}. Peak memory measured via tracemalloc (Sync client only).</p>
              <LazyChart render={() => {
                const {NumpyMemoryChart} = require('./charts/NumpyCharts');
                return <NumpyMemoryChart data={data} colorMode={colorMode} />;
              }} />
              <CollapsibleSection title="Memory Detail Table">
                <MemoryTable data={data} />
              </CollapsibleSection>
            </TabItem>
          )}
        </Tabs>
      </div>

      {/* Takeaways */}
      {data.takeaways.length > 0 && (
        <>
          <h3>NumPy Key Takeaways</h3>
          <ul className={cardStyles.takeawaysList}>
            {data.takeaways.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// ── Helper Functions ────────────────────────────────────────

function extractNumpySummary(data: NumpyBenchmarkData) {
  const metrics: Array<{value: string; label: string; color: 'primary' | 'success' | 'warning'}> = [];

  // Memory savings
  if (data.memory?.data?.length) {
    const maxSavings = Math.max(...data.memory.data.map((d) => d.savings_pct));
    if (maxSavings > 0) {
      metrics.push({value: `${maxSavings.toFixed(0)}%`, label: 'MAX MEMORY SAVINGS', color: 'primary'});
    }
  }

  // Best speedup from record scaling
  if (data.record_scaling?.data?.length) {
    let bestRatio = 0;
    for (const entry of data.record_scaling.data) {
      const dictMs = entry.batch_read_sync.avg_ms;
      const npMs = entry.batch_read_numpy_sync.avg_ms;
      if (dictMs && npMs && npMs > 0) {
        const ratio = dictMs / npMs;
        if (ratio > bestRatio) bestRatio = ratio;
      }
      const dictAsyncMs = entry.batch_read_async.avg_ms;
      const npAsyncMs = entry.batch_read_numpy_async.avg_ms;
      if (dictAsyncMs && npAsyncMs && npAsyncMs > 0) {
        const ratio = dictAsyncMs / npAsyncMs;
        if (ratio > bestRatio) bestRatio = ratio;
      }
    }
    if (bestRatio > 1.0) {
      metrics.push({value: `${bestRatio.toFixed(1)}x`, label: 'BEST NUMPY SPEEDUP', color: 'success'});
    }
  }

  // Number of scenarios
  let scenarioCount = 0;
  if (data.record_scaling) scenarioCount++;
  if (data.bin_scaling) scenarioCount++;
  if (data.post_processing) scenarioCount++;
  if (data.memory) scenarioCount++;
  metrics.push({value: `${scenarioCount}`, label: 'NUMPY SCENARIOS', color: 'warning'});

  return metrics;
}

// ── Table Components ────────────────────────────────────────

interface NumpyComparisonRow {
  key: string | number;
  label: string;
  batch_read_sync: {avg_ms: number | null} | undefined;
  batch_read_numpy_sync: {avg_ms: number | null} | undefined;
  batch_read_async: {avg_ms: number | null} | undefined;
  batch_read_numpy_async: {avg_ms: number | null} | undefined;
}

function NumpyComparisonTable({xHeader, rows}: {xHeader: string; rows: NumpyComparisonRow[]}) {
  return (
    <DataTable>
      <thead>
        <tr>
          <th>{xHeader}</th>
          <th>batch_read (Sync)</th>
          <th>numpy (Sync)</th>
          <th>batch_read (Async)</th>
          <th>numpy (Async)</th>
          <th>Speedup (Sync)</th>
          <th>Speedup (Async)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const brSync = row.batch_read_sync?.avg_ms ?? null;
          const npSync = row.batch_read_numpy_sync?.avg_ms ?? null;
          const brAsync = row.batch_read_async?.avg_ms ?? null;
          const npAsync = row.batch_read_numpy_async?.avg_ms ?? null;
          const spSync = calcNumpySpeedup(npSync, brSync);
          const spAsync = calcNumpySpeedup(npAsync, brAsync);

          return (
            <tr key={row.key}>
              <td data-label={xHeader}>{row.label}</td>
              <td data-label="batch_read (Sync)" className={tableStyles.numCell}>{fmtMs(brSync)}</td>
              <td data-label="numpy (Sync)" className={tableStyles.numCell}>{fmtMs(npSync)}</td>
              <td data-label="batch_read (Async)" className={tableStyles.numCell}>{fmtMs(brAsync)}</td>
              <td data-label="numpy (Async)" className={tableStyles.numCell}>{fmtMs(npAsync)}</td>
              <td data-label="Speedup (Sync)" className={`${tableStyles.numCell} ${tableStyles[spSync.className]}`}>{spSync.text}</td>
              <td data-label="Speedup (Async)" className={`${tableStyles.numCell} ${tableStyles[spAsync.className]}`}>{spAsync.text}</td>
            </tr>
          );
        })}
      </tbody>
    </DataTable>
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
  const rows: NumpyComparisonRow[] = section.data.map((entry: any) => ({
    key: entry[valueKey],
    label: entry[valueKey].toLocaleString(),
    batch_read_sync: entry.batch_read_sync,
    batch_read_numpy_sync: entry.batch_read_numpy_sync,
    batch_read_async: entry.batch_read_async,
    batch_read_numpy_async: entry.batch_read_numpy_async,
  }));
  return <NumpyComparisonTable xHeader={xLabel} rows={rows} />;
}

function PostProcessingTable({data}: {data: NumpyBenchmarkData}) {
  if (!data.post_processing) return null;
  const rows: NumpyComparisonRow[] = data.post_processing.data.map((entry) => ({
    key: entry.stage,
    label: entry.stage_label,
    batch_read_sync: entry.batch_read_sync,
    batch_read_numpy_sync: entry.batch_read_numpy_sync,
    batch_read_async: entry.batch_read_async,
    batch_read_numpy_async: entry.batch_read_numpy_async,
  }));
  return <NumpyComparisonTable xHeader="Stage" rows={rows} />;
}

function MemoryTable({data}: {data: NumpyBenchmarkData}) {
  if (!data.memory) return null;

  return (
    <DataTable>
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
          const savingsClass = entry.savings_pct > 0 ? 'faster' : entry.savings_pct < 0 ? 'slower' : '';
          return (
            <tr key={entry.record_count}>
              <td data-label="Records">{entry.record_count.toLocaleString()}</td>
              <td data-label="dict peak" className={tableStyles.numCell}>{entry.dict_peak_kb.toLocaleString()} KB</td>
              <td data-label="numpy peak" className={tableStyles.numCell}>{entry.numpy_peak_kb.toLocaleString()} KB</td>
              <td data-label="Savings" className={`${tableStyles.numCell} ${tableStyles[savingsClass]}`}>{fmtPct(entry.savings_pct)}</td>
            </tr>
          );
        })}
      </tbody>
    </DataTable>
  );
}
