import React from 'react';
import styles from './styles/Cards.module.css';

interface Props {
  value: string;
  label: string;
  color?: 'primary' | 'success' | 'warning';
}

const colorClassMap = {
  primary: styles.metricValuePrimary,
  success: styles.metricValueSuccess,
  warning: styles.metricValueWarning,
};

export default function MetricCard({value, label, color = 'primary'}: Props) {
  return (
    <div className={styles.metricCard}>
      <div className={`${styles.metricValue} ${colorClassMap[color]}`}>{value}</div>
      <div className={styles.metricLabel}>{label}</div>
    </div>
  );
}
