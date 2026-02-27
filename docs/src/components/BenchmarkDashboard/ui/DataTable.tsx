import React from 'react';
import tableStyles from '../styles/Tables.module.css';

export function DataTable({compact, children}: {compact?: boolean; children: React.ReactNode}) {
  const cls = [tableStyles.table, tableStyles.responsiveTable, compact && tableStyles.compactTable].filter(Boolean).join(' ');
  return (
    <div className={tableStyles.tableWrap}>
      <table className={cls}>{children}</table>
    </div>
  );
}
