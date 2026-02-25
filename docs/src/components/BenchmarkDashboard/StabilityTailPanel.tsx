import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import CollapsibleSection from './ui/CollapsibleSection';
import {fmtMs, fmtPct, fmtEff} from './helpers';
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
  const hasC = data.c_sync != null;
  const ops = OPERATIONS.filter(
    (op) =>
      data.rust_sync[op]?.cpu_p50_ms != null ||
      data.rust_sync[op]?.process_cpu_ms != null,
  );
  if (ops.length === 0) return null;

  return (
    <div className={tableStyles.tableWrap}>
      <table className={`${tableStyles.table} ${tableStyles.compactTable} ${tableStyles.responsiveTable}`}>
        <thead>
          <tr>
            <th>Operation</th>
            <th>Wall p50</th>
            <th>Thr.CPU</th>
            <th>Proc.CPU</th>
            <th>Proc.CPU%</th>
            <th>Ops/CPU-s</th>
            {hasC && <th>Off.Wall</th>}
            {hasC && <th>Off.Proc</th>}
            {hasC && <th>Off.CPU%</th>}
            {hasC && <th>Off.Ops/CPU</th>}
            {hasC && <th>Eff. vs Official</th>}
          </tr>
        </thead>
        <tbody>
          {ops.map((op) => {
            const sm = data.rust_sync[op];
            const cm = hasC ? data.c_sync![op] : null;
            const rustWall = sm?.p50_ms ?? sm?.avg_ms;

            let effComp: SpeedupResult | null = null;
            if (cm != null) {
              const rustEff = sm?.ops_per_cpu_sec;
              const cEff = cm?.ops_per_cpu_sec;
              if (rustEff != null && cEff != null && cEff > 0) {
                const pct = ((rustEff - cEff) / cEff) * 100;
                if (pct >= 0) {
                  effComp = {text: `+${pct.toFixed(0)}% more efficient`, className: 'faster'};
                } else {
                  effComp = {text: `${pct.toFixed(0)}% less efficient`, className: 'slower'};
                }
              }
            }

            return (
              <tr key={op}>
                <td data-label="Operation">{OP_LABELS[op]}</td>
                <td data-label="Wall p50" className={tableStyles.numCell}>{fmtMs(rustWall)}</td>
                <td data-label="Thr.CPU" className={tableStyles.numCell}>{fmtMs(sm?.cpu_p50_ms)}</td>
                <td data-label="Proc.CPU" className={tableStyles.numCell}>{fmtMs(sm?.process_cpu_ms)}</td>
                <td data-label="Proc.CPU%" className={tableStyles.numCell}>{fmtPct(sm?.process_cpu_pct)}</td>
                <td data-label="Ops/CPU-s" className={tableStyles.numCell}>{fmtEff(sm?.ops_per_cpu_sec)}</td>
                {hasC && <td data-label="Off.Wall" className={tableStyles.numCell}>{fmtMs(cm?.p50_ms ?? cm?.avg_ms)}</td>}
                {hasC && <td data-label="Off.Proc" className={tableStyles.numCell}>{fmtMs(cm?.process_cpu_ms)}</td>}
                {hasC && <td data-label="Off.CPU%" className={tableStyles.numCell}>{fmtPct(cm?.process_cpu_pct)}</td>}
                {hasC && <td data-label="Off.Ops/CPU" className={tableStyles.numCell}>{fmtEff(cm?.ops_per_cpu_sec)}</td>}
                {hasC && (
                  <td data-label="Eff. vs Official" className={`${tableStyles.numCell} ${effComp ? tableStyles[effComp.className] : ''}`}>
                    {effComp?.text ?? '-'}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p style={{fontSize: '0.85em', color: 'var(--ifm-color-emphasis-600)', marginTop: 4}}>
        Thr.CPU: Python calling thread CPU only. Proc.CPU: entire process CPU (Tokio workers included).
        Proc.CPU% can exceed 100% with multiple threads. Ops/CPU-s: operations per CPU-second (higher = more efficient).
      </p>
    </div>
  );
}

export default function StabilityTailPanel({data, colorMode}: Props) {
  const hasTail = OPERATIONS.some((op) => data.rust_sync[op]?.p50_ms != null);
  const hasCpu = OPERATIONS.some((op) => data.rust_sync[op]?.cpu_p50_ms != null || data.rust_sync[op]?.process_cpu_ms != null);

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
          <h3>CPU Efficiency</h3>
          <p className={dashStyles.sectionDesc}>
            Process-level CPU measurement (all threads including Tokio workers) via <code>resource.getrusage(RUSAGE_SELF)</code>.
            Ops/CPU-sec = operations per CPU-second (higher = more efficient).
          </p>
          <BrowserOnly fallback={<div style={{height: 350}}>Loading chart...</div>}>
            {() => {
              const {CpuComparisonChart} = require('./charts/CpuComparisonChart');
              return <CpuComparisonChart data={data} colorMode={colorMode} />;
            }}
          </BrowserOnly>
          <CollapsibleSection title="CPU Efficiency Detail Table">
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
