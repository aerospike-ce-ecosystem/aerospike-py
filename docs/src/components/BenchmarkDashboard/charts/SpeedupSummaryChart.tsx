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
  ReferenceLine,
} from 'recharts';
import {ChartTooltip, themeColors} from './shared';
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE, COLOR_SYNC, COLOR_ASYNC} from '../constants';
import type {FullBenchmarkData, ColorMode} from '../types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export function SpeedupSummaryChart({data, colorMode}: Props) {
  if (!data.c_sync) return null;

  const theme = themeColors(colorMode);

  const chartData = OPERATIONS
    .filter((op) => {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      return data.c_sync![officialOp]?.avg_ms != null;
    })
    .map((op) => {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      const officialVal = data.c_sync![officialOp]?.avg_ms ?? 1;
      const syncVal = data.rust_sync[op]?.avg_ms ?? 0;
      const asyncVal = data.rust_async[op]?.avg_ms ?? 0;

      return {
        operation: OP_LABELS[op],
        'Sync Speedup': syncVal > 0 ? officialVal / syncVal : 0,
        'Async Speedup': asyncVal > 0 ? officialVal / asyncVal : 0,
      };
    });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 60 + 80)}>
        <BarChart data={chartData} layout="vertical" margin={{top: 20, right: 40, left: 100, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis
            type="number"
            tick={{fill: theme.text}}
            label={{value: 'Speedup vs Official', position: 'insideBottom', offset: -5, fill: theme.text}}
          />
          <YAxis type="category" dataKey="operation" tick={{fill: theme.text}} width={90} />
          <Tooltip
            content={
              <SpeedupTooltip colorMode={colorMode} />
            }
          />
          <Legend wrapperStyle={{color: theme.text}} />
          <ReferenceLine x={1} stroke={theme.text} strokeDasharray="3 3" strokeWidth={2} label={{value: 'baseline', fill: theme.text, fontSize: 11}} />
          <Bar dataKey="Sync Speedup" name="Sync vs Official" fill={COLOR_SYNC} barSize={20} />
          <Bar dataKey="Async Speedup" name="Async vs Official" fill={COLOR_ASYNC} barSize={20} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SpeedupTooltip({
  active,
  payload,
  label,
  colorMode,
}: {
  active?: boolean;
  payload?: Array<{name: string; value: number; color: string}>;
  label?: string;
  colorMode: ColorMode;
}) {
  if (!active || !payload?.length) return null;
  const theme = themeColors(colorMode);
  return (
    <div
      style={{
        background: theme.tooltipBg,
        border: `1px solid ${theme.tooltipBorder}`,
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 13,
      }}
    >
      <p style={{margin: 0, fontWeight: 600, color: theme.text}}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{margin: '4px 0 0', color: entry.color}}>
          {entry.name}: {entry.value.toFixed(2)}x {entry.value >= 1.0 ? 'faster' : 'slower'}
        </p>
      ))}
    </div>
  );
}
