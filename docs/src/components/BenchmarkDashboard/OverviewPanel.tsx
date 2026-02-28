import React from 'react';
import {LazyChart} from './ui/LazyChart';
import type {ColorMode, FullBenchmarkData} from './types';
import {OPERATIONS, OP_LABELS, COLOR_APY_SYNC, COLOR_OFFICIAL_SYNC, COLOR_OFFICIAL_ASYNC, COLOR_APY_ASYNC} from './constants';
import {fmtMs, fmtOps, calcSpeedup, hasOfficialData, getMetric, getOfficialMetric} from './helpers';
import styles from './styles/Cards.module.css';
import tableStyles from './styles/Tables.module.css';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

// ── Inline Helper Components ────────────────────────────────

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
    <div className={styles.comparisonRow}>
      <span className={`${styles.comparisonRowLabel} ${styles.clientRowLabel}`}>
        <span className={styles.colorDot} style={{background: color}} />
        {label}
      </span>
      <span className={styles.clientRowValues}>
        <span className={`${styles.comparisonRowValue} ${styles.clientRowValue}`}>{fmtMs(latency)}</span>
        <span className={`${styles.comparisonRowValue} ${styles.clientRowValue}`}>{fmtOps(ops)}</span>
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
    <div className={styles.comparisonRow}>
      <span className={styles.comparisonRowLabel}>{label}</span>
      <span className={`${styles.comparisonRowValue} ${tableStyles[result.className] || ''}`}>
        {result.text}
      </span>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────

export default function OverviewPanel({data, colorMode}: Props) {
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
      <div className={styles.comparisonGrid}>
        {OPERATIONS.map((op) => {
          // Use p50 when available, fall back to avg (bulk ops have no p50)
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

          // Skip ops with no data at all
          if (syncLatency == null && asyncLatency == null && syncOps == null && asyncOps == null) return null;

          return (
            <div key={op} className={styles.comparisonCard}>
              <div className={styles.comparisonCardHeader}>{OP_LABELS[op]}</div>

              {/* 4-client rows */}
              <ClientRow color={COLOR_APY_SYNC} label="APY Sync" latency={syncLatency} ops={syncOps} />
              {hasOfficial && (
                <ClientRow color={COLOR_OFFICIAL_SYNC} label="Official Sync" latency={officialLatency.sync} ops={officialOps.sync} />
              )}
              {hasOfficial && (
                <ClientRow color={COLOR_OFFICIAL_ASYNC} label="Off. Async" latency={officialLatency.async_} ops={officialOps.async_} />
              )}
              <ClientRow color={COLOR_APY_ASYNC} label="APY Async" latency={asyncLatency} ops={asyncOps} />

              {/* Speedup comparisons */}
              {hasOfficial && (
                <div className={styles.speedupDivider}>
                  <SpeedupRow label="Sync vs Official" target={syncLatency} baseline={officialLatency.sync} />
                  <SpeedupRow label="Async vs Official" target={asyncLatency} baseline={officialLatency.async_} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Key Takeaways */}
      <h3>Key Takeaways</h3>
      <ul className={styles.takeawaysList}>
        {data.takeaways.map((t, i) => (
          <li key={i} dangerouslySetInnerHTML={{__html: t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}} />
        ))}
      </ul>
    </div>
  );
}
