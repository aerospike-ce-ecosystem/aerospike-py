import React from 'react';
import CollapsibleSection from './ui/CollapsibleSection';
import {DataTable} from './ui/DataTable';
import {LazyChart} from './ui/LazyChart';
import {fmtMs, fmtOps} from './helpers';
import tableStyles from './styles/Tables.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import type {FullBenchmarkData, ColorMode, HighConcurrencyEntry} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

function HighConcurrencyTable({data}: {data: FullBenchmarkData}) {
  const result = data.high_concurrency_scaling!;
  const hasOfficial = result.has_official;
  return (
    <DataTable>
      <thead>
        <tr>
          <th>Concurrency</th>
          <th>APY ops/s</th>
          <th>APY p99</th>
          {hasOfficial && <th>Off ops/s</th>}
          {hasOfficial && <th>Off p99</th>}
          {hasOfficial && <th>Speedup</th>}
        </tr>
      </thead>
      <tbody>
        {result.data.map((e: HighConcurrencyEntry) => {
          const apyOps = e.aerospike_py?.ops_per_sec ?? null;
          const offOps = e.official?.ops_per_sec ?? null;
          const speedup = apyOps && offOps && offOps > 0 ? `${(apyOps / offOps).toFixed(1)}x` : '-';
          return (
            <tr key={e.concurrency}>
              <td data-label="Concurrency" className={tableStyles.numCell}>{e.concurrency}</td>
              <td data-label="APY ops/s" className={tableStyles.numCell}>{fmtOps(apyOps)}</td>
              <td data-label="APY p99" className={tableStyles.numCell}>{fmtMs(e.aerospike_py?.per_op?.p99_ms)}</td>
              {hasOfficial && <td data-label="Off ops/s" className={tableStyles.numCell}>{fmtOps(offOps)}</td>}
              {hasOfficial && <td data-label="Off p99" className={tableStyles.numCell}>{fmtMs(e.official?.per_op?.p99_ms)}</td>}
              {hasOfficial && <td data-label="Speedup" className={tableStyles.numCell}>{speedup}</td>}
            </tr>
          );
        })}
      </tbody>
    </DataTable>
  );
}

function MixedWorkloadTable({data}: {data: FullBenchmarkData}) {
  const result = data.mixed_workload!;
  return (
    <DataTable>
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
    </DataTable>
  );
}

export default function ConcurrencyPanel({data, colorMode}: Props) {
  return (
    <div>
      {/* High Concurrency Scaling */}
      {data.high_concurrency_scaling && (
        <div className={dashStyles.scenarioCard}>
          <h3>High Concurrency Scaling</h3>
          <p className={dashStyles.sectionDesc}>
            Head-to-head: aerospike-py AsyncClient vs Official <code>run_in_executor</code> at concurrency levels: {data.high_concurrency_scaling.data.map((d: HighConcurrencyEntry) => d.concurrency).join(', ')}.
            ({data.high_concurrency_scaling.count.toLocaleString()} ops x {data.high_concurrency_scaling.rounds} rounds)
            {data.high_concurrency_scaling.has_official && ' Includes official client comparison.'}
          </p>
          <h4>Throughput vs Concurrency</h4>
          <LazyChart render={() => {
            const {HighConcurrencyThroughputChart} = require('./charts/HighConcurrencyCharts');
            return <HighConcurrencyThroughputChart result={data.high_concurrency_scaling} colorMode={colorMode} />;
          }} />
          <h4>p99 Latency vs Concurrency</h4>
          <LazyChart render={() => {
            const {HighConcurrencyLatencyChart} = require('./charts/HighConcurrencyCharts');
            return <HighConcurrencyLatencyChart result={data.high_concurrency_scaling} colorMode={colorMode} />;
          }} />
          <CollapsibleSection title="High Concurrency Detail Table">
            <HighConcurrencyTable data={data} />
          </CollapsibleSection>
        </div>
      )}

      {/* Mixed Workload */}
      {data.mixed_workload && (
        <div className={dashStyles.scenarioCard}>
          <h3>Mixed Workload</h3>
          <p className={dashStyles.sectionDesc}>
            Simulates realistic read/write mix with separate latency tracking
            ({data.mixed_workload.count.toLocaleString()} ops x {data.mixed_workload.rounds} rounds,
            concurrency={data.mixed_workload.concurrency}, AsyncClient).
          </p>
          <h4>Throughput by Workload Mix</h4>
          <LazyChart height={350} render={() => {
            const {MixedWorkloadChart} = require('./charts/MixedWorkloadCharts');
            return <MixedWorkloadChart result={data.mixed_workload} colorMode={colorMode} />;
          }} />
          <h4>Read/Write Latency Distribution</h4>
          <LazyChart height={350} render={() => {
            const {MixedLatencyChart} = require('./charts/MixedWorkloadCharts');
            return <MixedLatencyChart result={data.mixed_workload} colorMode={colorMode} />;
          }} />
          <CollapsibleSection title="Mixed Workload Detail Table">
            <MixedWorkloadTable data={data} />
          </CollapsibleSection>
        </div>
      )}
    </div>
  );
}
