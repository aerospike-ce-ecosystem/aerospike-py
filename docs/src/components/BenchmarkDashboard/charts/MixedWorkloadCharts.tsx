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
import {COLOR_THROUGHPUT, COLOR_READ, COLOR_WRITE} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {MixedResult, ColorMode} from '../types';

interface Props {
  result: MixedResult;
  colorMode: ColorMode;
}

export function MixedWorkloadChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => ({
    workload: shortLabel(d.label),
    Throughput: d.throughput_ops_sec,
  }));

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="workload" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Throughput (ops/sec)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ops" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Throughput" fill={COLOR_THROUGHPUT} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MixedLatencyChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => ({
    workload: shortLabel(d.label),
    'Read p50': d.read?.p50_ms ?? 0,
    'Read p95': d.read?.p95_ms ?? 0,
    'Write p50': d.write?.p50_ms ?? 0,
    'Write p95': d.write?.p95_ms ?? 0,
  }));

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="workload" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="Read p50" fill={COLOR_READ} fillOpacity={0.7} />
          <Bar dataKey="Read p95" fill={COLOR_READ} fillOpacity={1.0} />
          <Bar dataKey="Write p50" fill={COLOR_WRITE} fillOpacity={0.7} />
          <Bar dataKey="Write p95" fill={COLOR_WRITE} fillOpacity={1.0} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
