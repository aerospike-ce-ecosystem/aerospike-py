import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import CollapsibleSection from './ui/CollapsibleSection';
import {fmtMs, fmtOps, calcSpeedup} from './helpers';
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
  const hasC = data.c_sync != null;
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
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
            const officialOp = CROSS_OP_BASELINE[op] ?? op;
            const isCrossOp = officialOp !== op;
            const cv = hasC ? (data.c_sync![officialOp]?.[metric] ?? null) : null;
            const rustVsC = hasC ? calcSpeedup(rv, cv, latency) : null;
            const asyncVsC = hasC ? calcSpeedup(av, cv, latency) : null;

            return (
              <tr key={op}>
                <td data-label="Operation">{OP_LABELS[op]}{isCrossOp ? ' *' : ''}</td>
                <td data-label="SyncClient" className={tableStyles.numCell}>{formatter(rv)}</td>
                {hasC && <td data-label="Official" className={tableStyles.numCell}>{isCrossOp ? `${formatter(cv)} \u2020` : formatter(cv)}</td>}
                <td data-label="AsyncClient" className={tableStyles.numCell}>{formatter(av)}</td>
                {hasC && (
                  <td data-label="Sync vs Official" className={`${tableStyles.numCell} ${tableStyles[rustVsC!.className]}`}>
                    {rustVsC!.text}
                  </td>
                )}
                {hasC && (
                  <td data-label="Async vs Official" className={`${tableStyles.numCell} ${tableStyles[asyncVsC!.className]}`}>
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
          * BATCH_READ_NUMPY is compared against Official's BATCH_READ (&dagger; same data, different return format: numpy structured array vs Python dict)
        </p>
      )}
    </div>
  );
}

export default function LatencyThroughputPanel({data, colorMode}: Props) {
  return (
    <div>
      <h3>Latency Comparison</h3>
      <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
        {() => {
          const {LatencyChart} = require('./charts/LatencyChart');
          return <LatencyChart data={data} colorMode={colorMode} />;
        }}
      </BrowserOnly>
      <CollapsibleSection title="Latency Detail Table">
        <ComparisonTable data={data} metric="avg_ms" formatter={fmtMs} latency={true} />
      </CollapsibleSection>

      <h3>Throughput Comparison</h3>
      <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
        {() => {
          const {ThroughputChart} = require('./charts/ThroughputChart');
          return <ThroughputChart data={data} colorMode={colorMode} />;
        }}
      </BrowserOnly>
      <CollapsibleSection title="Throughput Detail Table">
        <ComparisonTable data={data} metric="ops_per_sec" formatter={fmtOps} latency={false} />
      </CollapsibleSection>
    </div>
  );
}
