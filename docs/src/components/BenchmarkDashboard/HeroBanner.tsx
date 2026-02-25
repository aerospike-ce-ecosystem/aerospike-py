import React from 'react';
import styles from './styles/HeroBanner.module.css';
import MetricCard from './MetricCard';
import EnvironmentBadge from './EnvironmentBadge';
import DateSelector from './DateSelector';
import {extractHeroMetrics} from './helpers';
import type {FullBenchmarkData} from './types';
import type {ReportEntry} from './hooks';

interface Props {
  data: FullBenchmarkData;
  dates: ReportEntry[];
  selectedDate: string | null;
  onDateChange: (date: string) => void;
}

export default function HeroBanner({data, dates, selectedDate, onDateChange}: Props) {
  const metrics = extractHeroMetrics(data);

  return (
    <div className={styles.heroBanner}>
      <div className={styles.heroHeader}>
        <h3 className={styles.heroTitle}>aerospike-py Benchmark</h3>
        <div className={styles.heroRight}>
          <DateSelector dates={dates} selectedDate={selectedDate} onChange={onDateChange} />
          <EnvironmentBadge env={data.environment} />
        </div>
      </div>
      <div className={styles.metricsGrid}>
        {metrics.map((m, i) => (
          <MetricCard key={i} value={m.value} label={m.label} color={m.color} />
        ))}
      </div>
    </div>
  );
}
