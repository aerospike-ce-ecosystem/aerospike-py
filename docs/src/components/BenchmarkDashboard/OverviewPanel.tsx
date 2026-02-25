import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import type {ColorMode, FullBenchmarkData} from './types';
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE} from './constants';
import {fmtMs, fmtOps, calcSpeedup} from './helpers';
import styles from './styles/Cards.module.css';
import tableStyles from './styles/Tables.module.css';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export default function OverviewPanel({data, colorMode}: Props) {
  const hasC = data.c_sync != null;

  return (
    <div>
      {/* Speedup Summary Chart */}
      {hasC && (
        <BrowserOnly fallback={<div style={{height: 400}}>Loading chart...</div>}>
          {() => {
            const {SpeedupSummaryChart} = require('./charts/SpeedupSummaryChart');
            return <SpeedupSummaryChart data={data} colorMode={colorMode} />;
          }}
        </BrowserOnly>
      )}

      {/* Quick Comparison Grid */}
      <h3>Quick Comparison</h3>
      <div className={styles.comparisonGrid}>
        {OPERATIONS.map((op) => {
          const syncAvg = data.rust_sync[op]?.avg_ms ?? null;
          const asyncAvg = data.rust_async[op]?.avg_ms ?? null;
          const syncOps = data.rust_sync[op]?.ops_per_sec ?? null;
          const asyncOps = data.rust_async[op]?.ops_per_sec ?? null;

          const officialOp = CROSS_OP_BASELINE[op] ?? op;
          const officialAvg = hasC ? (data.c_sync![officialOp]?.avg_ms ?? null) : null;
          const officialOpsVal = hasC ? (data.c_sync![officialOp]?.ops_per_sec ?? null) : null;

          const syncVsOfficial = hasC ? calcSpeedup(syncAvg, officialAvg, true) : null;
          const asyncVsOfficial = hasC ? calcSpeedup(asyncAvg, officialAvg, true) : null;

          // Skip ops with no data
          if (syncAvg == null && asyncAvg == null) return null;

          return (
            <div key={op} className={styles.comparisonCard}>
              <div className={styles.comparisonCardHeader}>{OP_LABELS[op]}</div>

              <div className={styles.comparisonRow}>
                <span className={styles.comparisonRowLabel}>Sync</span>
                <span className={styles.comparisonRowValue}>{fmtMs(syncAvg)}</span>
              </div>
              <div className={styles.comparisonRow}>
                <span className={styles.comparisonRowLabel}>Sync ops/s</span>
                <span className={styles.comparisonRowValue}>{fmtOps(syncOps)}</span>
              </div>

              {hasC && (
                <>
                  <div className={styles.comparisonRow}>
                    <span className={styles.comparisonRowLabel}>Official</span>
                    <span className={styles.comparisonRowValue}>{fmtMs(officialAvg)}</span>
                  </div>
                  <div className={styles.comparisonRow}>
                    <span className={styles.comparisonRowLabel}>Official ops/s</span>
                    <span className={styles.comparisonRowValue}>{fmtOps(officialOpsVal)}</span>
                  </div>
                </>
              )}

              <div className={styles.comparisonRow}>
                <span className={styles.comparisonRowLabel}>Async</span>
                <span className={styles.comparisonRowValue}>{fmtMs(asyncAvg)}</span>
              </div>
              <div className={styles.comparisonRow}>
                <span className={styles.comparisonRowLabel}>Async ops/s</span>
                <span className={styles.comparisonRowValue}>{fmtOps(asyncOps)}</span>
              </div>

              {hasC && syncVsOfficial && (
                <div className={styles.comparisonRow} style={{marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--ifm-color-emphasis-200)'}}>
                  <span className={styles.comparisonRowLabel}>Sync vs Official</span>
                  <span className={`${styles.comparisonRowValue} ${tableStyles[syncVsOfficial.className]}`}>
                    {syncVsOfficial.text}
                  </span>
                </div>
              )}
              {hasC && asyncVsOfficial && (
                <div className={styles.comparisonRow}>
                  <span className={styles.comparisonRowLabel}>Async vs Official</span>
                  <span className={`${styles.comparisonRowValue} ${tableStyles[asyncVsOfficial.className]}`}>
                    {asyncVsOfficial.text}
                  </span>
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
