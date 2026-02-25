import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {ChartTooltip, themeColors} from './shared';
import {OPERATIONS, OP_LABELS, COLOR_SYNC, COLOR_OFFICIAL, COLOR_ASYNC} from '../constants';
import type {FullBenchmarkData, ColorMode} from '../types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export function CpuComparisonChart({data, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasC = data.c_sync != null;

  const ops = OPERATIONS.filter(
    (op) => data.rust_sync[op]?.process_cpu_pct != null || data.rust_sync[op]?.cpu_pct != null,
  );
  if (ops.length === 0) return null;

  const chartData = ops.map((op) => {
    const entry: Record<string, string | number> = {
      operation: OP_LABELS[op],
      'Sync Proc.CPU%': data.rust_sync[op]?.process_cpu_pct ?? 0,
    };
    if (hasC) {
      entry['Official Proc.CPU%'] = data.c_sync![op]?.process_cpu_pct ?? 0;
    }
    entry['Async Proc.CPU%'] = data.rust_async[op]?.process_cpu_pct ?? 0;
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 350, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            domain={[0, 'auto']}
            label={{value: 'Process CPU %', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="pct" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync Proc.CPU%" name="SyncClient" fill={COLOR_SYNC} />
          {hasC && <Bar dataKey="Official Proc.CPU%" name="Official" fill={COLOR_OFFICIAL} />}
          <Bar dataKey="Async Proc.CPU%" name="AsyncClient" fill={COLOR_ASYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
