import React, {useState} from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import CollapsibleSection from './ui/CollapsibleSection';
import {fmtMs, fmtOps, fmtKb, fmtPct} from './helpers';
import tableStyles from './styles/Tables.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import type {FullBenchmarkData, ColorMode, DataSizeEntry, ConcurrencyEntry} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export default function AdvancedPanel({data, colorMode}: Props) {
  const hasDataSize = !!data.data_size;
  const hasConcurrency = !!data.concurrency_scaling;
  const hasMemory = !!data.memory_profiling;
  const hasMixed = !!data.mixed_workload;
  const hasAny = hasDataSize || hasConcurrency || hasMemory || hasMixed;

  if (!hasAny) {
    return (
      <div style={{padding: '2rem', textAlign: 'center', color: 'var(--ifm-color-emphasis-600)'}}>
        No advanced profiling data available for this benchmark run.
        <br />Run <code>make run-benchmark-report BENCH_SCENARIO=all</code> to generate advanced results.
      </div>
    );
  }

  return (
    <div className={dashStyles.innerTabs}>
      <Tabs groupId="advanced">
        {hasDataSize && (
          <TabItem value="datasize" label="Data Size">
            <div className={dashStyles.scenarioCard}>
              <h3>Data Size Scaling</h3>
              <p className={dashStyles.sectionDesc}>
                PUT/GET latency across different record sizes ({data.data_size!.count.toLocaleString()} ops x {data.data_size!.rounds} rounds).
              </p>
              <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
                {() => {
                  const {DataSizeChart} = require('./charts/DataSizeCharts');
                  return <DataSizeChart result={data.data_size} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <CollapsibleSection title="Data Size Detail Table">
                <DataSizeTable data={data} />
              </CollapsibleSection>
              {data.data_size!.data.some((d: DataSizeEntry) => d.put.cpu_pct != null) && (
                <>
                  <h4>CPU Utilization by Data Size</h4>
                  <BrowserOnly fallback={<div style={{height: 300}}>Loading chart...</div>}>
                    {() => {
                      const {DataSizeCpuChart} = require('./charts/DataSizeCharts');
                      return <DataSizeCpuChart result={data.data_size} colorMode={colorMode} />;
                    }}
                  </BrowserOnly>
                </>
              )}
            </div>
          </TabItem>
        )}

        {hasConcurrency && (
          <TabItem value="concurrency" label="Concurrency">
            <div className={dashStyles.scenarioCard}>
              <h3>Concurrency Scaling</h3>
              <p className={dashStyles.sectionDesc}>
                AsyncClient throughput and per-op latency at concurrency levels: {data.concurrency_scaling!.data.map((d: ConcurrencyEntry) => d.concurrency).join(', ')}.
                ({data.concurrency_scaling!.count.toLocaleString()} ops x {data.concurrency_scaling!.rounds} rounds)
              </p>
              <h4>Throughput vs Concurrency</h4>
              <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
                {() => {
                  const {ConcurrencyThroughputChart} = require('./charts/ConcurrencyCharts');
                  return <ConcurrencyThroughputChart result={data.concurrency_scaling} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <h4>Latency vs Concurrency</h4>
              <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
                {() => {
                  const {ConcurrencyLatencyChart} = require('./charts/ConcurrencyCharts');
                  return <ConcurrencyLatencyChart result={data.concurrency_scaling} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <CollapsibleSection title="Concurrency Detail Table">
                <ConcurrencyTable data={data} />
              </CollapsibleSection>
            </div>
          </TabItem>
        )}

        {hasMemory && (
          <TabItem value="memory" label="Memory">
            <div className={dashStyles.scenarioCard}>
              <h3>Memory Profiling</h3>
              <p className={dashStyles.sectionDesc}>
                Peak memory per operation type across data sizes ({data.memory_profiling!.count.toLocaleString()} ops).
                Measured via <code>tracemalloc</code>.
                {data.memory_profiling!.has_c && ' Includes official C client comparison.'}
              </p>
              <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
                {() => {
                  const {MemoryProfileChart} = require('./charts/MemoryProfileChart');
                  return <MemoryProfileChart result={data.memory_profiling} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <CollapsibleSection title="Memory Detail Table">
                <MemoryTable data={data} />
              </CollapsibleSection>
            </div>
          </TabItem>
        )}

        {hasMixed && (
          <TabItem value="mixed" label="Mixed Workload">
            <div className={dashStyles.scenarioCard}>
              <h3>Mixed Workload</h3>
              <p className={dashStyles.sectionDesc}>
                Simulates realistic read/write mix with separate latency tracking
                ({data.mixed_workload!.count.toLocaleString()} ops x {data.mixed_workload!.rounds} rounds,
                concurrency={data.mixed_workload!.concurrency}, AsyncClient).
              </p>
              <h4>Throughput by Workload Mix</h4>
              <BrowserOnly fallback={<div style={{height: 350}}>Loading chart...</div>}>
                {() => {
                  const {MixedWorkloadChart} = require('./charts/MixedWorkloadCharts');
                  return <MixedWorkloadChart result={data.mixed_workload} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <h4>Read/Write Latency Distribution</h4>
              <BrowserOnly fallback={<div style={{height: 350}}>Loading chart...</div>}>
                {() => {
                  const {MixedLatencyChart} = require('./charts/MixedWorkloadCharts');
                  return <MixedLatencyChart result={data.mixed_workload} colorMode={colorMode} />;
                }}
              </BrowserOnly>
              <CollapsibleSection title="Mixed Workload Detail Table">
                <MixedWorkloadTable data={data} />
              </CollapsibleSection>
            </div>
          </TabItem>
        )}
      </Tabs>
    </div>
  );
}

// ── Inline Table Components ─────────────────────────────────

function DataSizeTable({data}: {data: FullBenchmarkData}) {
  const result = data.data_size!;
  const hasCpu = result.data.some((d) => d.put.cpu_pct != null);
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Profile</th>
            <th>PUT p50</th>
            <th>PUT p99</th>
            {hasCpu && <th>PUT CPU%</th>}
            <th>GET p50</th>
            <th>GET p99</th>
            {hasCpu && <th>GET CPU%</th>}
          </tr>
        </thead>
        <tbody>
          {result.data.map((e) => (
            <tr key={e.label}>
              <td data-label="Profile">{e.label}</td>
              <td data-label="PUT p50" className={tableStyles.numCell}>{fmtMs(e.put.p50_ms)}</td>
              <td data-label="PUT p99" className={tableStyles.numCell}>{fmtMs(e.put.p99_ms)}</td>
              {hasCpu && <td data-label="PUT CPU%" className={tableStyles.numCell}>{fmtPct(e.put.cpu_pct)}</td>}
              <td data-label="GET p50" className={tableStyles.numCell}>{fmtMs(e.get.p50_ms)}</td>
              <td data-label="GET p99" className={tableStyles.numCell}>{fmtMs(e.get.p99_ms)}</td>
              {hasCpu && <td data-label="GET CPU%" className={tableStyles.numCell}>{fmtPct(e.get.cpu_pct)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConcurrencyTable({data}: {data: FullBenchmarkData}) {
  const result = data.concurrency_scaling!;
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Concurrency</th>
            <th>PUT ops/s</th>
            <th>PUT p50</th>
            <th>PUT p95</th>
            <th>PUT p99</th>
            <th>GET ops/s</th>
            <th>GET p50</th>
            <th>GET p95</th>
            <th>GET p99</th>
          </tr>
        </thead>
        <tbody>
          {result.data.map((e) => {
            const pp = e.put.per_op ?? {};
            const gp = e.get.per_op ?? {};
            return (
              <tr key={e.concurrency}>
                <td data-label="Concurrency" className={tableStyles.numCell}>{e.concurrency}</td>
                <td data-label="PUT ops/s" className={tableStyles.numCell}>{fmtOps(e.put.ops_per_sec)}</td>
                <td data-label="PUT p50" className={tableStyles.numCell}>{fmtMs(pp.p50_ms)}</td>
                <td data-label="PUT p95" className={tableStyles.numCell}>{fmtMs(pp.p95_ms)}</td>
                <td data-label="PUT p99" className={tableStyles.numCell}>{fmtMs(pp.p99_ms)}</td>
                <td data-label="GET ops/s" className={tableStyles.numCell}>{fmtOps(e.get.ops_per_sec)}</td>
                <td data-label="GET p50" className={tableStyles.numCell}>{fmtMs(gp.p50_ms)}</td>
                <td data-label="GET p95" className={tableStyles.numCell}>{fmtMs(gp.p95_ms)}</td>
                <td data-label="GET p99" className={tableStyles.numCell}>{fmtMs(gp.p99_ms)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MemoryTable({data}: {data: FullBenchmarkData}) {
  const result = data.memory_profiling!;
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Profile</th>
            <th>PUT peak</th>
            <th>GET peak</th>
            <th>BATCH peak</th>
            {result.has_c && <th>Official GET</th>}
            {result.has_c && <th>Official BATCH</th>}
          </tr>
        </thead>
        <tbody>
          {result.data.map((e) => (
            <tr key={e.label}>
              <td data-label="Profile">{e.label}</td>
              <td data-label="PUT peak" className={tableStyles.numCell}>{fmtKb(e.put_peak_kb)}</td>
              <td data-label="GET peak" className={tableStyles.numCell}>{fmtKb(e.get_peak_kb)}</td>
              <td data-label="BATCH peak" className={tableStyles.numCell}>{fmtKb(e.batch_read_peak_kb)}</td>
              {result.has_c && <td data-label="Official GET" className={tableStyles.numCell}>{fmtKb(e.c_get_peak_kb)}</td>}
              {result.has_c && <td data-label="Official BATCH" className={tableStyles.numCell}>{fmtKb(e.c_batch_read_peak_kb)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MixedWorkloadTable({data}: {data: FullBenchmarkData}) {
  const result = data.mixed_workload!;
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Workload</th>
            <th>Throughput</th>
            <th>Read p50</th>
            <th>Read p95</th>
            <th>Read p99</th>
            <th>Write p50</th>
            <th>Write p95</th>
            <th>Write p99</th>
          </tr>
        </thead>
        <tbody>
          {result.data.map((e) => (
            <tr key={e.label}>
              <td data-label="Workload">{e.label}</td>
              <td data-label="Throughput" className={tableStyles.numCell}>{fmtOps(e.throughput_ops_sec)}</td>
              <td data-label="Read p50" className={tableStyles.numCell}>{fmtMs(e.read?.p50_ms)}</td>
              <td data-label="Read p95" className={tableStyles.numCell}>{fmtMs(e.read?.p95_ms)}</td>
              <td data-label="Read p99" className={tableStyles.numCell}>{fmtMs(e.read?.p99_ms)}</td>
              <td data-label="Write p50" className={tableStyles.numCell}>{fmtMs(e.write?.p50_ms)}</td>
              <td data-label="Write p95" className={tableStyles.numCell}>{fmtMs(e.write?.p95_ms)}</td>
              <td data-label="Write p99" className={tableStyles.numCell}>{fmtMs(e.write?.p99_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
