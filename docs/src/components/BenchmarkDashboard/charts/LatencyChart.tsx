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
  LabelList,
} from 'recharts';
import {ChartTooltip, themeColors, speedupLabel} from './shared';
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE, COLOR_SYNC, COLOR_OFFICIAL, COLOR_ASYNC} from '../constants';
import type {FullBenchmarkData, ColorMode} from '../types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export function LatencyChart({data, colorMode}: Props) {
  const hasC = data.c_sync != null;
  const theme = themeColors(colorMode);

  const chartData = OPERATIONS.map((op) => {
    const syncVal = data.rust_sync[op]?.avg_ms ?? 0;
    const asyncVal = data.rust_async[op]?.avg_ms ?? 0;
    const officialOp = CROSS_OP_BASELINE[op] ?? op;
    const officialVal = hasC ? (data.c_sync![officialOp]?.avg_ms ?? 0) : 0;

    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      Sync: syncVal,
      Async: asyncVal,
    };
    if (hasC) {
      entry.Official = officialVal;
      entry.syncLabel = speedupLabel(syncVal, officialVal, true);
      entry.asyncLabel = speedupLabel(asyncVal, officialVal, true);
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 30, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync" name="aerospike-py (SyncClient)" fill={COLOR_SYNC}>
            {hasC && <LabelList dataKey="syncLabel" position="top" fill={COLOR_SYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
          {hasC && <Bar dataKey="Official" name="aerospike (official)" fill={COLOR_OFFICIAL} />}
          <Bar dataKey="Async" name="aerospike-py (AsyncClient)" fill={COLOR_ASYNC}>
            {hasC && <LabelList dataKey="asyncLabel" position="top" fill={COLOR_ASYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
