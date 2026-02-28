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
import {OPERATIONS, OP_LABELS, CROSS_OP_BASELINE, COLOR_APY_SYNC, COLOR_APY_ASYNC} from '../constants';
import {hasOfficialData} from '../helpers';
import chartStyles from '../styles/Charts.module.css';
import type {FullBenchmarkData, ColorMode} from '../types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

export function SpeedupSummaryChart({data, colorMode}: Props) {
  const hasOfficial = hasOfficialData(data);
  if (!hasOfficial) return null;

  const theme = themeColors(colorMode);

  const chartData = OPERATIONS
    .filter((op) => {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      const officialSyncVal = data.official_sync?.[officialOp]?.avg_ms;
      const officialAsyncVal = data.official_async?.[officialOp]?.avg_ms;
      return officialSyncVal != null || officialAsyncVal != null;
    })
    .map((op) => {
      const officialOp = CROSS_OP_BASELINE[op] ?? op;
      const officialVal = data.official_sync?.[officialOp]?.avg_ms ?? data.official_async?.[officialOp]?.avg_ms ?? 1;
      const syncVal = data.aerospike_py_sync[op]?.avg_ms ?? 0;
      const asyncVal = data.aerospike_py_async[op]?.avg_ms ?? 0;

      return {
        operation: OP_LABELS[op],
        'Sync Speedup': syncVal > 0 ? officialVal / syncVal : 0,
        'Async Speedup': asyncVal > 0 ? officialVal / asyncVal : 0,
      };
    });

  return (
    <div className={chartStyles.chartWrap}>
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
              <ChartTooltip
                colorMode={colorMode}
                unit="x"
                formatter={(_name, value) => `${value.toFixed(2)}x ${value >= 1.0 ? 'faster' : 'slower'}`}
              />
            }
          />
          <Legend wrapperStyle={{color: theme.text}} />
          <ReferenceLine x={1} stroke={theme.text} strokeDasharray="3 3" strokeWidth={2} label={{value: 'baseline', fill: theme.text, fontSize: 11}} />
          <Bar dataKey="Sync Speedup" name="Sync vs Official" fill={COLOR_APY_SYNC} barSize={20} />
          <Bar dataKey="Async Speedup" name="Async vs Official" fill={COLOR_APY_ASYNC} barSize={20} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
