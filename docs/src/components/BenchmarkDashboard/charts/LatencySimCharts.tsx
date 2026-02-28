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
import {COLOR_APY_ASYNC, COLOR_OFFICIAL_ASYNC} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {LatencySimResult, ColorMode} from '../types';

interface Props {
  result: LatencySimResult;
  colorMode: ColorMode;
}

export function LatencySimThroughputChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasOfficial = result.has_official;

  const chartData = result.data.map((d) => ({
    rtt: d.rtt_ms,
    'aerospike-py': d.aerospike_py?.ops_per_sec ?? null,
    ...(hasOfficial && d.official ? {'Official (run_in_executor)': d.official?.ops_per_sec ?? null} : {}),
  }));

  return (
    <div className={chartStyles.chartWrap}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 25}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis
            dataKey="rtt"
            tick={{fill: theme.text}}
            label={{value: 'Network RTT (ms)', position: 'insideBottom', offset: -10, fill: theme.text}}
          />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Throughput (ops/sec)', angle: -90, position: 'insideLeft', fill: theme.text}}
            tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ops" />} />
          <Legend wrapperStyle={{color: theme.text}} />
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
              dataKey="Official (run_in_executor)"
              stroke={COLOR_OFFICIAL_ASYNC}
              strokeWidth={2.5}
              dot={{r: 4}}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      <p style={{textAlign: 'center', fontSize: '0.75rem', color: theme.text, opacity: 0.7, marginTop: 4}}>
        (Simulated) — asyncio.sleep injected to model RTT impact on thread pool vs Tokio architecture
      </p>
    </div>
  );
}
