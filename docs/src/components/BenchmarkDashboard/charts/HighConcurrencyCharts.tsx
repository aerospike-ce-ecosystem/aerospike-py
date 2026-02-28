import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import {ChartTooltip, themeColors} from './shared';
import {COLOR_APY_ASYNC, COLOR_OFFICIAL_ASYNC} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {HighConcurrencyResult, ColorMode} from '../types';

interface Props {
  result: HighConcurrencyResult;
  colorMode: ColorMode;
}

export function HighConcurrencyThroughputChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasOfficial = result.has_official;

  const chartData = result.data.map((d) => ({
    concurrency: d.concurrency,
    'aerospike-py': d.aerospike_py?.ops_per_sec ?? null,
    ...(hasOfficial && d.official ? {'Official': d.official?.ops_per_sec ?? null} : {}),
  }));

  const apyFailConc = result.data.find((d) => !(d.aerospike_py?.ops_per_sec))?.concurrency;
  const offFailConc = hasOfficial ? result.data.find((d) => !(d.official?.ops_per_sec))?.concurrency : undefined;

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis
            dataKey="concurrency"
            tick={{fill: theme.text}}
            label={{value: 'Concurrent Requests', position: 'insideBottom', offset: -5, fill: theme.text}}
          />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Throughput (ops/sec)', angle: -90, position: 'insideLeft', fill: theme.text}}
            tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ops" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          {apyFailConc !== undefined && (
            <ReferenceLine
              x={apyFailConc}
              stroke={COLOR_APY_ASYNC}
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{value: '✕ APY failed', position: 'insideTopRight', fill: COLOR_APY_ASYNC, fontSize: 11}}
            />
          )}
          {offFailConc !== undefined && hasOfficial && (
            <ReferenceLine
              x={offFailConc}
              stroke={COLOR_OFFICIAL_ASYNC}
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{value: '✕ Official failed', position: 'insideTopLeft', fill: COLOR_OFFICIAL_ASYNC, fontSize: 11}}
            />
          )}
          <Line
            type="monotone"
            dataKey="aerospike-py"
            stroke={COLOR_APY_ASYNC}
            strokeWidth={2.5}
            dot={{r: 4}}
            connectNulls={false}
          />
          {hasOfficial && (
            <Line
              type="monotone"
              dataKey="Official"
              stroke={COLOR_OFFICIAL_ASYNC}
              strokeWidth={2.5}
              dot={{r: 4}}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HighConcurrencyLatencyChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasOfficial = result.has_official;

  const chartData = result.data.map((d) => ({
    concurrency: d.concurrency,
    'aerospike-py p99': d.aerospike_py?.per_op?.p99_ms ?? null,
    ...(hasOfficial && d.official ? {'Official p99': d.official?.per_op?.p99_ms ?? null} : {}),
  }));

  const apyFailConc = result.data.find((d) => !(d.aerospike_py?.per_op?.p99_ms))?.concurrency;
  const offFailConc = hasOfficial ? result.data.find((d) => !(d.official?.per_op?.p99_ms))?.concurrency : undefined;

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis
            dataKey="concurrency"
            tick={{fill: theme.text}}
            label={{value: 'Concurrent Requests', position: 'insideBottom', offset: -5, fill: theme.text}}
          />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'p99 Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          {apyFailConc !== undefined && (
            <ReferenceLine
              x={apyFailConc}
              stroke={COLOR_APY_ASYNC}
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{value: '✕ APY failed', position: 'insideTopRight', fill: COLOR_APY_ASYNC, fontSize: 11}}
            />
          )}
          {offFailConc !== undefined && hasOfficial && (
            <ReferenceLine
              x={offFailConc}
              stroke={COLOR_OFFICIAL_ASYNC}
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{value: '✕ Official failed', position: 'insideTopLeft', fill: COLOR_OFFICIAL_ASYNC, fontSize: 11}}
            />
          )}
          <Line
            type="monotone"
            dataKey="aerospike-py p99"
            stroke={COLOR_APY_ASYNC}
            strokeWidth={2.5}
            dot={{r: 4}}
            connectNulls={false}
          />
          {hasOfficial && (
            <Line
              type="monotone"
              dataKey="Official p99"
              stroke={COLOR_OFFICIAL_ASYNC}
              strokeWidth={2.5}
              dot={{r: 4}}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
