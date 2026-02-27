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
import {shortLabel} from '../helpers';
import {COLOR_PUT_P50, COLOR_PUT_P99, COLOR_GET_P50, COLOR_GET_P99} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {DataSizeResult, ColorMode} from '../types';

interface Props {
  result: DataSizeResult;
  colorMode: ColorMode;
}

export function DataSizeChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => ({
    profile: shortLabel(d.label),
    'PUT p50': d.put.p50_ms ?? 0,
    'PUT p99': d.put.p99_ms ?? 0,
    'GET p50': d.get.p50_ms ?? 0,
    'GET p99': d.get.p99_ms ?? 0,
  }));

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="profile" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="PUT p50" fill={COLOR_PUT_P50} />
          <Bar dataKey="PUT p99" fill={COLOR_PUT_P99} />
          <Bar dataKey="GET p50" fill={COLOR_GET_P50} />
          <Bar dataKey="GET p99" fill={COLOR_GET_P99} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
