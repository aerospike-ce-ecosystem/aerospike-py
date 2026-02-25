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
import {COLOR_MEM_PUT, COLOR_MEM_GET, COLOR_MEM_BATCH, COLOR_MEM_C_GET, COLOR_MEM_C_BATCH} from '../constants';
import type {MemoryResult, ColorMode} from '../types';

interface Props {
  result: MemoryResult;
  colorMode: ColorMode;
}

export function MemoryProfileChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);

  const chartData = result.data.map((d) => {
    const entry: Record<string, unknown> = {
      profile: d.label.split(' (')[0],
      'PUT peak': d.put_peak_kb,
      'GET peak': d.get_peak_kb,
      'BATCH peak': d.batch_read_peak_kb,
    };
    if (result.has_c && d.c_get_peak_kb != null) {
      entry['Official GET'] = d.c_get_peak_kb;
    }
    if (result.has_c && d.c_batch_read_peak_kb != null) {
      entry['Official BATCH'] = d.c_batch_read_peak_kb;
    }
    return entry;
  });

  return (
    <div style={{width: '100%', minHeight: 400, margin: '1rem 0'}}>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{top: 20, right: 30, left: 20, bottom: 5}}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
          <XAxis dataKey="profile" tick={{fill: theme.text}} />
          <YAxis
            tick={{fill: theme.text}}
            label={{value: 'Peak Memory (KB)', angle: -90, position: 'insideLeft', fill: theme.text}}
          />
          <Tooltip content={<ChartTooltip colorMode={colorMode} unit="kb" />} />
          <Legend wrapperStyle={{color: theme.text}} />
          <Bar dataKey="PUT peak" fill={COLOR_MEM_PUT} />
          <Bar dataKey="GET peak" fill={COLOR_MEM_GET} />
          <Bar dataKey="BATCH peak" fill={COLOR_MEM_BATCH} />
          {result.has_c && <Bar dataKey="Official GET" fill={COLOR_MEM_C_GET} />}
          {result.has_c && <Bar dataKey="Official BATCH" fill={COLOR_MEM_C_BATCH} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
