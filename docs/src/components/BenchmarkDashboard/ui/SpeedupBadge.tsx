import React from 'react';
import styles from '../styles/Cards.module.css';

interface Props {
  ratio: number;
  label?: string;
}

export default function SpeedupBadge({ratio, label}: Props) {
  if (ratio <= 0) return <span>-</span>;

  const isFaster = ratio >= 1.0;
  const displayRatio = isFaster ? ratio : 1 / ratio;
  const text = label ?? `${displayRatio.toFixed(1)}x ${isFaster ? 'faster' : 'slower'}`;

  return (
    <span className={`${styles.speedupBadge} ${isFaster ? styles.speedupFaster : styles.speedupSlower}`}>
      {text}
    </span>
  );
}
