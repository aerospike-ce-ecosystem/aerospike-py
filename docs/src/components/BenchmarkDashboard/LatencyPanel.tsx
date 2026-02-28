import React from 'react';
import CollapsibleSection from './ui/CollapsibleSection';
import {DataTable} from './ui/DataTable';
import {LazyChart} from './ui/LazyChart';
import {fmtMs, fmtOps, calcSpeedup, hasOfficialData, getMetric, getOfficialMetric} from './helpers';
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE, COLOR_APY_SYNC, COLOR_OFFICIAL_SYNC, COLOR_OFFICIAL_ASYNC, COLOR_APY_ASYNC} from './constants';
import tableStyles from './styles/Tables.module.css';
import cardStyles from './styles/Cards.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import type {FullBenchmarkData, ColorMode} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

// -- Client Row (from OverviewPanel) --------------------------

function ClientRow({
  color,
  label,
  latency,
  ops,
}: {
  color: string;
  label: string;
  latency: number | null;
  ops: number | null;
}) {
  return (
    <div className={cardStyles.comparisonRow}>
      <span className={`${cardStyles.comparisonRowLabel} ${cardStyles.clientRowLabel}`}>
        <span className={cardStyles.colorDot} style={{background: color}} />
        {label}
      </span>
      <span className={cardStyles.clientRowValues}>
        <span className={`${cardStyles.comparisonRowValue} ${cardStyles.clientRowValue}`}>{fmtMs(latency)}</span>
        <span className={`${cardStyles.comparisonRowValue} ${cardStyles.clientRowValue}`}>{fmtOps(ops)}</span>
      </span>
    </div>
  );
}

function SpeedupRow({
  label,
  target,
  baseline,
}: {
  label: string;
  target: number | null;
  baseline: number | null;
}) {
  const result = calcSpeedup(target, baseline, true);
  return (
    <div className={cardStyles.comparisonRow}>
      <span className={cardStyles.comparisonRowLabel}>{label}</span>
      <span className={`${cardStyles.comparisonRowValue} ${tableStyles[result.className] || ''}`}>
        {result.text}
      </span>
    </div>
  );
}

// -- Comparison Table (from LatencyThroughputPanel) -----------

function ComparisonTable({
  data,
  metric,
  formatter,
  latency,
}: {
  data: FullBenchmarkData;
  metric: 'avg_ms' | 'ops_per_sec';
  formatter: (v: number | null) => string;
  latency: boolean;
}) {
  const hasOfficial = hasOfficialData(data);
  return (
    <>
      <DataTable>
        <thead>
          <tr>
            <th>Operation</th>
            <th>aerospike-py (SyncClient)</th>
            {hasOfficial && <th>Official (Sync)</th>}
            {hasOfficial && <th>Official (Async)</th>}
            <th>aerospike-py (AsyncClient)</th>
            {hasOfficial && <th>Sync vs Official</th>}
            {hasOfficial && <th>Async vs Official</th>}
          </tr>
        </thead>
        <tbody>
          {OPERATIONS.map((op) => {
            const rv = getMetric(data.aerospike_py_sync, op, metric);
            const av = getMetric(data.aerospike_py_async, op, metric);
            const officialOp = CROSS_OP_BASELINE[op] ?? op;
            const isCrossOp = officialOp !== op;
            const official = getOfficialMetric(data, op, metric);
            const officialSyncVal = official.sync;
            const officialAsyncVal = official.async_;
            const syncVsOfficial = hasOfficial ? calcSpeedup(rv, official.baseline, latency) : null;
            const asyncVsOfficial = hasOfficial ? calcSpeedup(av, official.baseline, latency) : null;

            return (
              <tr key={op}>
                <td data-label="Operation">{OP_LABELS[op]}{isCrossOp ? ' *' : ''}</td>
                <td data-label="SyncClient" className={tableStyles.numCell}>{formatter(rv)}</td>
                {hasOfficial && <td data-label="Official Sync" className={tableStyles.numCell}>{isCrossOp ? `${formatter(officialSyncVal)} \u2020` : formatter(officialSyncVal)}</td>}
                {hasOfficial && <td data-label="Official Async" className={tableStyles.numCell}>{isCrossOp ? `${formatter(officialAsyncVal)} \u2020` : formatter(officialAsyncVal)}</td>}
                <td data-label="AsyncClient" className={tableStyles.numCell}>{formatter(av)}</td>
                {hasOfficial && (
                  <td data-label="Sync vs Official" className={`${tableStyles.numCell} ${tableStyles[syncVsOfficial!.className]}`}>
                    {syncVsOfficial!.text}
                  </td>
                )}
                {hasOfficial && (
                  <td data-label="Async vs Official" className={`${tableStyles.numCell} ${tableStyles[asyncVsOfficial!.className]}`}>
                    {asyncVsOfficial!.text}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </DataTable>
      {hasOfficial && (
        <p className={tableStyles.footnote}>
          * BATCH_READ_NUMPY is compared against Official's BATCH_READ (&dagger; same data, different return format: numpy structured array vs Python dict)
        </p>
      )}
    </>
  );
}

// -- Data Size Table ------------------------------------------

function DataSizeTable({data}: {data: FullBenchmarkData}) {
  const result = data.data_size!;
  return (
    <DataTable>
      <thead>
        <tr>
          <th>Profile</th>
          <th>PUT p50</th>
          <th>PUT p99</th>
          <th>GET p50</th>
          <th>GET p99</th>
        </tr>
      </thead>
      <tbody>
        {result.data.map((e) => (
          <tr key={e.label}>
            <td data-label="Profile">{e.label}</td>
            <td data-label="PUT p50" className={tableStyles.numCell}>{fmtMs(e.put.p50_ms)}</td>
            <td data-label="PUT p99" className={tableStyles.numCell}>{fmtMs(e.put.p99_ms)}</td>
            <td data-label="GET p50" className={tableStyles.numCell}>{fmtMs(e.get.p50_ms)}</td>
            <td data-label="GET p99" className={tableStyles.numCell}>{fmtMs(e.get.p99_ms)}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

// -- Latency Sim Table ----------------------------------------

function LatencySimTable({data}: {data: FullBenchmarkData}) {
  const result = data.latency_sim!;
  const hasOfficial = result.has_official;
  return (
    <DataTable>
      <thead>
        <tr>
          <th>RTT (ms)</th>
          <th>APY ops/s</th>
          <th>APY p99</th>
          {hasOfficial && <th>Off ops/s</th>}
          {hasOfficial && <th>Off p99</th>}
          {hasOfficial && <th>Speedup</th>}
        </tr>
      </thead>
      <tbody>
        {result.data.map((e) => {
          const apyOps = e.aerospike_py?.ops_per_sec ?? null;
          const offOps = e.official?.ops_per_sec ?? null;
          const speedup = apyOps && offOps && offOps > 0 ? `${(apyOps / offOps).toFixed(1)}x` : '-';
          return (
            <tr key={e.rtt_ms}>
              <td data-label="RTT (ms)" className={tableStyles.numCell}>{e.rtt_ms.toFixed(1)}</td>
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

// -- Main Component -------------------------------------------

export default function LatencyPanel({data, colorMode}: Props) {
  const hasOfficial = hasOfficialData(data);

  return (
    <div>
      {/* Speedup Summary Chart */}
      {hasOfficial && (
        <LazyChart render={() => {
          const {SpeedupSummaryChart} = require('./charts/SpeedupSummaryChart');
          return <SpeedupSummaryChart data={data} colorMode={colorMode} />;
        }} />
      )}

      {/* Quick Comparison Grid */}
      <h3>Quick Comparison</h3>
      <div className={cardStyles.comparisonGrid}>
        {OPERATIONS.map((op) => {
          const syncLatency = getMetric(data.aerospike_py_sync, op, 'p50_ms') ?? getMetric(data.aerospike_py_sync, op, 'avg_ms');
          const asyncLatency = getMetric(data.aerospike_py_async, op, 'p50_ms') ?? getMetric(data.aerospike_py_async, op, 'avg_ms');
          const syncOps = getMetric(data.aerospike_py_sync, op, 'ops_per_sec');
          const asyncOps = getMetric(data.aerospike_py_async, op, 'ops_per_sec');

          const officialP50 = getOfficialMetric(data, op, 'p50_ms');
          const officialAvg = getOfficialMetric(data, op, 'avg_ms');
          const officialLatency = {
            sync: officialP50.sync ?? officialAvg.sync,
            async_: officialP50.async_ ?? officialAvg.async_,
          };
          const officialOps = getOfficialMetric(data, op, 'ops_per_sec');

          if (syncLatency == null && asyncLatency == null && syncOps == null && asyncOps == null) return null;

          return (
            <div key={op} className={cardStyles.comparisonCard}>
              <div className={cardStyles.comparisonCardHeader}>{OP_LABELS[op]}</div>

              <ClientRow color={COLOR_APY_SYNC} label="APY Sync" latency={syncLatency} ops={syncOps} />
              {hasOfficial && (
                <ClientRow color={COLOR_OFFICIAL_SYNC} label="Official Sync" latency={officialLatency.sync} ops={officialOps.sync} />
              )}
              {hasOfficial && (
                <ClientRow color={COLOR_OFFICIAL_ASYNC} label="Off. Async" latency={officialLatency.async_} ops={officialOps.async_} />
              )}
              <ClientRow color={COLOR_APY_ASYNC} label="APY Async" latency={asyncLatency} ops={asyncOps} />

              {hasOfficial && (
                <div className={cardStyles.speedupDivider}>
                  <SpeedupRow label="Sync vs Official" target={syncLatency} baseline={officialLatency.sync} />
                  <SpeedupRow label="Async vs Official" target={asyncLatency} baseline={officialLatency.async_} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Latency & Throughput Charts */}
      <h3>Latency Comparison</h3>
      <LazyChart render={() => {
        const {FourClientBarChart} = require('./charts/FourClientBarChart');
        return <FourClientBarChart data={data} colorMode={colorMode} metric="avg_ms" yLabel="Latency (ms)" unit="ms" lowerIsBetter={true} />;
      }} />
      <CollapsibleSection title="Latency Detail Table">
        <ComparisonTable data={data} metric="avg_ms" formatter={fmtMs} latency={true} />
      </CollapsibleSection>

      <h3>Throughput Comparison</h3>
      <LazyChart render={() => {
        const {FourClientBarChart} = require('./charts/FourClientBarChart');
        return <FourClientBarChart data={data} colorMode={colorMode} metric="ops_per_sec" yLabel="Throughput (ops/sec)" unit="ops" lowerIsBetter={false} />;
      }} />
      <CollapsibleSection title="Throughput Detail Table">
        <ComparisonTable data={data} metric="ops_per_sec" formatter={fmtOps} latency={false} />
      </CollapsibleSection>

      {/* Data Size Scaling */}
      {data.data_size && (
        <div className={dashStyles.scenarioCard}>
          <h3>Data Size Scaling</h3>
          <p className={dashStyles.sectionDesc}>
            PUT/GET latency across different record sizes ({data.data_size.count.toLocaleString()} ops x {data.data_size.rounds} rounds).
          </p>
          <LazyChart render={() => {
            const {DataSizeChart} = require('./charts/DataSizeCharts');
            return <DataSizeChart result={data.data_size} colorMode={colorMode} />;
          }} />
          <CollapsibleSection title="Data Size Detail Table">
            <DataSizeTable data={data} />
          </CollapsibleSection>
        </div>
      )}

      {/* Latency Simulation */}
      {data.latency_sim && (
        <div className={dashStyles.scenarioCard}>
          <h3>Latency Simulation</h3>
          <p className={dashStyles.sectionDesc}>
            Simulates network RTT by injecting <code>asyncio.sleep()</code> after each operation.
            Official async: sleep blocks OS thread (inside <code>run_in_executor</code>).
            aerospike-py: sleep yields event loop.
            (concurrency={data.latency_sim.concurrency}, {data.latency_sim.count.toLocaleString()} ops x {data.latency_sim.rounds} rounds)
          </p>
          <h4>Throughput vs Network RTT</h4>
          <LazyChart height={450} render={() => {
            const {LatencySimThroughputChart} = require('./charts/LatencySimCharts');
            return <LatencySimThroughputChart result={data.latency_sim} colorMode={colorMode} />;
          }} />
          <CollapsibleSection title="Latency Sim Detail Table">
            <LatencySimTable data={data} />
          </CollapsibleSection>
        </div>
      )}

      {/* Key Takeaways */}
      <h3>Key Takeaways</h3>
      <ul className={cardStyles.takeawaysList}>
        {data.takeaways.map((t, i) => (
          <li key={i} dangerouslySetInnerHTML={{__html: t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}} />
        ))}
      </ul>
    </div>
  );
}
