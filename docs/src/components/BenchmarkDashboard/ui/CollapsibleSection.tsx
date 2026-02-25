import React from 'react';
import styles from '../styles/Tables.module.css';

interface Props {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export default function CollapsibleSection({title, defaultOpen = false, children}: Props) {
  return (
    <details className={styles.collapsible} open={defaultOpen}>
      <summary className={styles.collapsibleSummary}>{title}</summary>
      <div className={styles.collapsibleContent}>{children}</div>
    </details>
  );
}
