import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {ChartTooltip, themeColors} from './shared';
import {COLOR_PUT_P50, COLOR_PUT_P99, COLOR_GET_P50, COLOR_GET_P99} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {ConcurrencyResult, ColorMode} from '../types';

interface Props {
  result: ConcurrencyResult;
  colorMode: ColorMode;
}

export function ConcurrencyThroughputChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => ({
    concurrency: d.concurrency.toString(),
    'PUT ops/s': d.put.ops_per_sec ?? 0,
    'GET ops/s': d.get.ops_per_sec ?? 0,
  }));

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="concurrency" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Throughput (ops/sec)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ops" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="PUT ops/s" stroke={COLOR_PUT_P50} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="GET ops/s" stroke={COLOR_GET_P50} strokeWidth={2} dot={{r: 4}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConcurrencyLatencyChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => {
    const pp = d.put.per_op ?? {};
    const gp = d.get.per_op ?? {};
    return {
      concurrency: d.concurrency.toString(),
      'PUT p50': pp.p50_ms ?? 0,
      'PUT p99': pp.p99_ms ?? 0,
      'GET p50': gp.p50_ms ?? 0,
      'GET p99': gp.p99_ms ?? 0,
    };
  });

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="concurrency" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="PUT p50" stroke={COLOR_PUT_P50} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="PUT p99" stroke={COLOR_PUT_P99} strokeWidth={2} strokeDasharray="5 5" dot={{r: 3}} />
          <Line type="monotone" dataKey="GET p50" stroke={COLOR_GET_P50} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="GET p99" stroke={COLOR_GET_P99} strokeWidth={2} strokeDasharray="5 5" dot={{r: 3}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
