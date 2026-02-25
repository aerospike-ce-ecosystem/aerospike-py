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
import {COLOR_PUT_P50, COLOR_PUT_P99, COLOR_GET_P50, COLOR_GET_P99} from '../constants';
import type {DataSizeResult, ColorMode} from '../types';

interface Props {
  result: DataSizeResult;
  colorMode: ColorMode;
}

export function DataSizeChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => ({
    profile: d.label.split(' (')[0],
    'PUT p50': d.put.p50_ms ?? 0,
    'PUT p99': d.put.p99_ms ?? 0,
    'GET p50': d.get.p50_ms ?? 0,
    'GET p99': d.get.p99_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
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

export function DataSizeCpuChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasCpu = result.data.some((d) => d.put.cpu_pct != null);
  if (!hasCpu) return null;

  const chartData = result.data.map((d) => ({
    profile: d.label.split(' (')[0],
    'PUT CPU%': d.put.cpu_pct ?? 0,
    'GET CPU%': d.get.cpu_pct ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 300, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="profile" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            domain={[0, 100]}
            label={{value: 'CPU %', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="pct" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="PUT CPU%" fill={COLOR_PUT_P50} fillOpacity={0.7} />
          <Bar dataKey="GET CPU%" fill={COLOR_GET_P50} fillOpacity={0.7} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
