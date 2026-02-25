import React from 'react';
import type {ReportEntry} from './hooks';
import styles from './styles/Charts.module.css';

interface Props {
  dates: ReportEntry[];
  selectedDate: string | null;
  onChange: (date: string) => void;
}

function formatDate(dateStr: string): string {
  // "2026-02-24_20-57" → "2026-02-24 20:57"
  return dateStr.replace('_', ' ').replace(/-(\d{2})$/, ':$1');
}

export default function DateSelector({dates, selectedDate, onChange}: Props) {
  if (dates.length <= 1) return null;

  return (
    <select
      className={styles.dateSelect}
      value={selectedDate ?? ''}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Select benchmark date"
    >
      {dates.map((d) => (
        <option key={d.date} value={d.date}>
          {formatDate(d.date)}
        </option>
      ))}
    </select>
  );
}
