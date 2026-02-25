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

export function TailLatencyChart({data, colorMode}: Props) {
  const hasC = data.c_sync != null;
  const theme = themeColors(colorMode);

  const ops = OPERATIONS.filter((op) => data.rust_sync[op]?.p50_ms != null);
  if (ops.length === 0) return null;

  const chartData = ops.map((op) => {
    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      'Sync p50': data.rust_sync[op]?.p50_ms ?? 0,
      'Sync p99': data.rust_sync[op]?.p99_ms ?? 0,
      'Async p50': data.rust_async[op]?.p50_ms ?? data.rust_async[op]?.per_op?.p50_ms ?? 0,
      'Async p99': data.rust_async[op]?.p99_ms ?? data.rust_async[op]?.per_op?.p99_ms ?? 0,
    };
    if (hasC) {
      entry['Official p50'] = data.c_sync![op]?.p50_ms ?? 0;
      entry['Official p99'] = data.c_sync![op]?.p99_ms ?? 0;
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync p50" fill={COLOR_SYNC} fillOpacity={0.6} />
          <Bar dataKey="Sync p99" fill={COLOR_SYNC} fillOpacity={1.0} />
          {hasC && <Bar dataKey="Official p50" fill={COLOR_OFFICIAL} fillOpacity={0.6} />}
          {hasC && <Bar dataKey="Official p99" fill={COLOR_OFFICIAL} fillOpacity={1.0} />}
          <Bar dataKey="Async p50" fill={COLOR_ASYNC} fillOpacity={0.6} />
          <Bar dataKey="Async p99" fill={COLOR_ASYNC} fillOpacity={1.0} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
