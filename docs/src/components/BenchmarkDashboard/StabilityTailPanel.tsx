import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import CollapsibleSection from './ui/CollapsibleSection';
import {fmtMs, fmtPct} from './helpers';
import {OPERATIONS, OP_LABELS} from './constants';
import tableStyles from './styles/Tables.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import type {FullBenchmarkData, ColorMode, SpeedupResult} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

function StabilityTable({data}: {data: FullBenchmarkData}) {
  const hasC = data.c_sync != null;
  const hasMad = OPERATIONS.some((op) => data.rust_sync[op]?.mad_ms != null);
  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Sync stdev</th>
            {hasMad && <th>Sync MAD</th>}
            {hasC && <th>Official stdev</th>}
            <th>Async stdev</th>
            {hasMad && <th>Async MAD</th>}
          </tr>
        </thead>
        <tbody>
          {OPERATIONS.map((op) => (
            <tr key={op}>
              <td data-label="Operation">{OP_LABELS[op]}</td>
              <td data-label="Sync stdev" className={tableStyles.numCell}>{fmtMs(data.rust_sync[op]?.stdev_ms ?? null)}</td>
              {hasMad && <td data-label="Sync MAD" className={tableStyles.numCell}>{fmtMs(data.rust_sync[op]?.mad_ms)}</td>}
              {hasC && <td data-label="Official stdev" className={tableStyles.numCell}>{fmtMs(data.c_sync![op]?.stdev_ms ?? null)}</td>}
              <td data-label="Async stdev" className={tableStyles.numCell}>{fmtMs(data.rust_async[op]?.stdev_ms ?? null)}</td>
              {hasMad && <td data-label="Async MAD" className={tableStyles.numCell}>{fmtMs(data.rust_async[op]?.mad_ms)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TailLatencyTable({data}: {data: FullBenchmarkData}) {
  const hasC = data.c_sync != null;
  const ops = OPERATIONS.filter((op) =>
    data.rust_sync[op]?.p50_ms != null ||
    data.rust_async[op]?.p50_ms != null ||
    data.rust_async[op]?.per_op?.p50_ms != null,
  );
  if (ops.length === 0) return null;

  const hasP95 = ops.some((op) =>
    data.rust_sync[op]?.p95_ms != null ||
    data.rust_async[op]?.p95_ms != null ||
    data.rust_async[op]?.per_op?.p95_ms != null,
  );

  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Sync p50</th>
            {hasP95 && <th>Sync p95</th>}
            <th>Sync p99</th>
            {hasC && <th>Official p50</th>}
            {hasC && hasP95 && <th>Official p95</th>}
            {hasC && <th>Official p99</th>}
            <th>Async p50</th>
            {hasP95 && <th>Async p95</th>}
            <th>Async p99</th>
          </tr>
        </thead>
        <tbody>
          {ops.map((op) => (
            <tr key={op}>
              <td data-label="Operation">{OP_LABELS[op]}</td>
              <td data-label="Sync p50" className={tableStyles.numCell}>{fmtMs(data.rust_sync[op]?.p50_ms)}</td>
              {hasP95 && <td data-label="Sync p95" className={tableStyles.numCell}>{fmtMs(data.rust_sync[op]?.p95_ms)}</td>}
              <td data-label="Sync p99" className={tableStyles.numCell}>{fmtMs(data.rust_sync[op]?.p99_ms)}</td>
              {hasC && <td data-label="Official p50" className={tableStyles.numCell}>{fmtMs(data.c_sync![op]?.p50_ms)}</td>}
              {hasC && hasP95 && <td data-label="Official p95" className={tableStyles.numCell}>{fmtMs(data.c_sync![op]?.p95_ms)}</td>}
              {hasC && <td data-label="Official p99" className={tableStyles.numCell}>{fmtMs(data.c_sync![op]?.p99_ms)}</td>}
              <td data-label="Async p50" className={tableStyles.numCell}>{fmtMs(data.rust_async[op]?.p50_ms ?? data.rust_async[op]?.per_op?.p50_ms)}</td>
              {hasP95 && <td data-label="Async p95" className={tableStyles.numCell}>{fmtMs(data.rust_async[op]?.p95_ms ?? data.rust_async[op]?.per_op?.p95_ms)}</td>}
              <td data-label="Async p99" className={tableStyles.numCell}>{fmtMs(data.rust_async[op]?.p99_ms ?? data.rust_async[op]?.per_op?.p99_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CpuBreakdownTable({data}: {data: FullBenchmarkData}) {
  const ops = OPERATIONS.filter(
    (op) => data.rust_sync[op]?.cpu_pct != null || data.rust_async[op]?.cpu_pct != null,
  );
  if (ops.length === 0) return null;

  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.compactTable} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Sync CPU p50</th>
            <th>Sync I/O Wait</th>
            <th>Sync CPU %</th>
            <th>Async CPU p50</th>
            <th>Async I/O Wait</th>
            <th>Async CPU %</th>
            <th>Comparison</th>
          </tr>
        </thead>
        <tbody>
          {ops.map((op) => {
            const sm = data.rust_sync[op];
            const am = data.rust_async[op];
            const syncCpu = sm?.cpu_pct;
            const asyncCpu = am?.cpu_pct;
            let cpuComp: SpeedupResult | null = null;
            if (syncCpu != null && asyncCpu != null && syncCpu > 0) {
              const ratio = syncCpu / asyncCpu;
              if (ratio >= 1.0) {
                const pct = (ratio - 1) * 100;
                cpuComp = {text: `Async ${pct.toFixed(0)}% less CPU`, className: 'faster'};
              } else {
                const pct = (1 / ratio - 1) * 100;
                cpuComp = {text: `Async ${pct.toFixed(0)}% more CPU`, className: 'slower'};
              }
            }
            return (
              <tr key={op}>
                <td data-label="Operation">{OP_LABELS[op]}</td>
                <td data-label="Sync CPU p50" className={tableStyles.numCell}>{fmtMs(sm?.cpu_p50_ms)}</td>
                <td data-label="Sync I/O Wait" className={tableStyles.numCell}>{fmtMs(sm?.io_wait_p50_ms)}</td>
                <td data-label="Sync CPU %" className={tableStyles.numCell}>{fmtPct(sm?.cpu_pct)}</td>
                <td data-label="Async CPU p50" className={tableStyles.numCell}>{fmtMs(am?.cpu_p50_ms)}</td>
                <td data-label="Async I/O Wait" className={tableStyles.numCell}>{fmtMs(am?.io_wait_p50_ms)}</td>
                <td data-label="Async CPU %" className={tableStyles.numCell}>{fmtPct(am?.cpu_pct)}</td>
                <td data-label="Comparison" className={`${tableStyles.numCell} ${cpuComp ? tableStyles[cpuComp.className] : ''}`}>
                  {cpuComp?.text ?? '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p style={{fontSize: '0.85em', color: 'var(--ifm-color-emphasis-600)', marginTop: 4}}>
        CPU % = CPU time / wall time. Lower values indicate more I/O-bound operations (network latency dominant).
        {' "less CPU" means AsyncClient uses less CPU time per operation than SyncClient.'}
      </p>
    </div>
  );
}

export default function StabilityTailPanel({data, colorMode}: Props) {
  const hasTail = OPERATIONS.some((op) => data.rust_sync[op]?.p50_ms != null);
  const hasCpu = OPERATIONS.some((op) => data.rust_sync[op]?.cpu_pct != null || data.rust_async[op]?.cpu_pct != null);

  return (
    <div>
      {hasTail && (
        <>
          <h3>Tail Latency Distribution</h3>
          <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
            {() => {
              const {TailLatencyChart} = require('./charts/TailLatencyChart');
              return <TailLatencyChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <CollapsibleSection title="Tail Latency Detail Table">
            <TailLatencyTable data={data} />
          </CollapsibleSection>
        </>
      )}

      {hasCpu && (
        <>
          <h3>CPU Time Breakdown</h3>
          <p className={dashStyles.sectionDesc}>
            Separates CPU computation time from I/O wait (network latency). Measured via <code>time.process_time()</code> vs <code>time.perf_counter()</code>.
          </p>
          <BrowserOnly fallback={<div style={{height: 350}}>Loading chart...</div>}>
            {() => {
              const {CpuComparisonChart} = require('./charts/CpuComparisonChart');
              return <CpuComparisonChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <CollapsibleSection title="CPU Breakdown Detail Table">
            <CpuBreakdownTable data={data} />
          </CollapsibleSection>
        </>
      )}

      <h3>Stability</h3>
      <CollapsibleSection title="Stability Detail Table" defaultOpen={true}>
        <StabilityTable data={data} />
      </CollapsibleSection>
    </div>
  );
}
