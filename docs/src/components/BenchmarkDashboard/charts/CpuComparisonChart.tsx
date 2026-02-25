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
import {OPERATIONS, OP_LABELS, COLOR_SYNC, COLOR_ASYNC} from '../constants';
import type {FullBenchmarkData, ColorMode} from '../types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export function CpuComparisonChart({data, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const ops = OPERATIONS.filter(
    (op) => data.rust_sync[op]?.cpu_pct != null || data.rust_async[op]?.cpu_pct != null,
  );
  if (ops.length === 0) return null;

  const chartData = ops.map((op) => ({
    operation: OP_LABELS[op],
    'Sync CPU%': data.rust_sync[op]?.cpu_pct ?? 0,
    'Async CPU%': data.rust_async[op]?.cpu_pct ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 350, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            domain={[0, 'auto']}
            label={{value: 'CPU %', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="pct" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync CPU%" name="SyncClient CPU%" fill={COLOR_SYNC} />
          <Bar dataKey="Async CPU%" name="AsyncClient CPU%" fill={COLOR_ASYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
