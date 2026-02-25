import React from 'react';
import {
  LineChart,
  Line,
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
import {COLOR_DICT_SYNC, COLOR_NUMPY_SYNC, COLOR_DICT_ASYNC, COLOR_NUMPY_ASYNC} from '../constants';
import type {NumpyBenchmarkData, ColorMode} from '../types';

interface Props {
  data: NumpyBenchmarkData;
  colorMode: ColorMode;
}

export function RecordScalingChart({data, colorMode}: Props) {
  if (!data.record_scaling) return null;
  const theme = themeColors(colorMode);

  const chartData = data.record_scaling.data.map((d) => ({
    records: d.record_count.toLocaleString(),
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="records" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="batch_read (Sync)" stroke={COLOR_DICT_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Sync)" stroke={COLOR_NUMPY_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="batch_read (Async)" stroke={COLOR_DICT_ASYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Async)" stroke={COLOR_NUMPY_ASYNC} strokeWidth={2} dot={{r: 4}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BinScalingChart({data, colorMode}: Props) {
  if (!data.bin_scaling) return null;
  const theme = themeColors(colorMode);

  const chartData = data.bin_scaling.data.map((d) => ({
    bins: d.bin_count.toString(),
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="bins" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Line type="monotone" dataKey="batch_read (Sync)" stroke={COLOR_DICT_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Sync)" stroke={COLOR_NUMPY_SYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="batch_read (Async)" stroke={COLOR_DICT_ASYNC} strokeWidth={2} dot={{r: 4}} />
          <Line type="monotone" dataKey="numpy (Async)" stroke={COLOR_NUMPY_ASYNC} strokeWidth={2} dot={{r: 4}} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PostProcessingChart({data, colorMode}: Props) {
  if (!data.post_processing) return null;
  const theme = themeColors(colorMode);

  const chartData = data.post_processing.data.map((d) => ({
    stage: d.stage_label,
    'batch_read (Sync)': d.batch_read_sync.avg_ms ?? 0,
    'numpy (Sync)': d.batch_read_numpy_sync.avg_ms ?? 0,
    'batch_read (Async)': d.batch_read_async.avg_ms ?? 0,
    'numpy (Async)': d.batch_read_numpy_async.avg_ms ?? 0,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="stage" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Latency (ms)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="ms" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="batch_read (Sync)" fill={COLOR_DICT_SYNC} />
          <Bar dataKey="numpy (Sync)" fill={COLOR_NUMPY_SYNC} />
          <Bar dataKey="batch_read (Async)" fill={COLOR_DICT_ASYNC} />
          <Bar dataKey="numpy (Async)" fill={COLOR_NUMPY_ASYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function NumpyMemoryChart({data, colorMode}: Props) {
  if (!data.memory) return null;
  const theme = themeColors(colorMode);

  const chartData = data.memory.data.map((d) => ({
    records: d.record_count.toLocaleString(),
    'dict (KB)': d.dict_peak_kb,
    'numpy (KB)': d.numpy_peak_kb,
  }));

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="records" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Peak Memory (KB)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="kb" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="dict (KB)" fill={COLOR_DICT_SYNC} />
          <Bar dataKey="numpy (KB)" fill={COLOR_NUMPY_SYNC} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
