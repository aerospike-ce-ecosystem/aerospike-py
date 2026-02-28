import React from 'react';
import CollapsibleSection from './ui/CollapsibleSection';
import {DataTable} from './ui/DataTable';
import {LazyChart} from './ui/LazyChart';
import {fmtMs, fmtOps, calcSpeedup, hasOfficialData, getMetric, getOfficialMetric} from './helpers';
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE} from './constants';
import tableStyles from './styles/Tables.module.css';
import type {FullBenchmarkData, ColorMode, SpeedupResult} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

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

export default function LatencyThroughputPanel({data, colorMode}: Props) {
  return (
    <div>
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
    </div>
  );
}
