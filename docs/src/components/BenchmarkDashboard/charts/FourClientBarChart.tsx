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
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE, COLOR_APY_SYNC, COLOR_OFFICIAL_SYNC, COLOR_OFFICIAL_ASYNC, COLOR_APY_ASYNC} from '../constants';
import {hasOfficialData} from '../helpers';
import chartStyles from '../styles/Charts.module.css';
import type {FullBenchmarkData, ColorMode} from '../types';

interface FourClientBarChartProps {
  data: FullBenchmarkData;
  colorMode: ColorMode;
  metric: 'avg_ms' | 'ops_per_sec';
  yLabel: string;
  unit: 'ms' | 'ops';
  lowerIsBetter: boolean;
}

export function FourClientBarChart({data, colorMode, metric, yLabel, unit, lowerIsBetter}: FourClientBarChartProps) {
  const hasOfficial = hasOfficialData(data);
  const theme = themeColors(colorMode);

  const chartData = OPERATIONS.map((op) => {
    const syncVal = data.aerospike_py_sync[op]?.[metric] ?? 0;
    const asyncVal = data.aerospike_py_async[op]?.[metric] ?? 0;
    const officialOp = CROSS_OP_BASELINE[op] ?? op;
    const officialSyncVal = data.official_sync ? (data.official_sync[officialOp]?.[metric] ?? 0) : 0;
    const officialAsyncVal = data.official_async ? (data.official_async[officialOp]?.[metric] ?? 0) : 0;

    const entry: Record<string, unknown> = {
      operation: OP_LABELS[op],
      Sync: syncVal,
      Async: asyncVal,
    };
    if (hasOfficial) {
      entry['Official Sync'] = officialSyncVal;
      entry['Official Async'] = officialAsyncVal;
      const baseline = officialSyncVal || officialAsyncVal;
      entry.syncLabel = speedupLabel(syncVal, baseline, lowerIsBetter);
      entry.asyncLabel = speedupLabel(asyncVal, baseline, lowerIsBetter);
    }
    return entry;
  });

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 30, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="operation" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: yLabel, angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit={unit} />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Sync" name="aerospike-py (SyncClient)" fill={COLOR_APY_SYNC}>
            {hasOfficial && <LabelList dataKey="syncLabel" position="top" fill={COLOR_APY_SYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
          {hasOfficial && <Bar dataKey="Official Sync" name="Official (Sync)" fill={COLOR_OFFICIAL_SYNC} />}
          {hasOfficial && <Bar dataKey="Official Async" name="Official (Async)" fill={COLOR_OFFICIAL_ASYNC} />}
          <Bar dataKey="Async" name="aerospike-py (AsyncClient)" fill={COLOR_APY_ASYNC}>
            {hasOfficial && <LabelList dataKey="asyncLabel" position="top" fill={COLOR_APY_ASYNC} fontSize={10} fontWeight="bold" />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
