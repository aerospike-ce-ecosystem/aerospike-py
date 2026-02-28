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
import {COLOR_MEM_PUT, COLOR_MEM_GET, COLOR_MEM_BATCH, COLOR_MEM_C_GET, COLOR_MEM_C_BATCH} from '../constants';
import chartStyles from '../styles/Charts.module.css';
import type {MemoryResult, ColorMode} from '../types';

interface Props {
  result: MemoryResult;
  colorMode: ColorMode;
}

export function MemoryProfileChart({result, colorMode}: Props) {
  const theme = themeColors(colorMode);
  const hasOfficial = result.has_official ?? result.has_c;

  const chartData = result.data.map((d) => {
    const entry: Record<string, unknown> = {
      profile: shortLabel(d.label),
      'PUT peak': d.put_peak_kb,
      'GET peak': d.get_peak_kb,
      'BATCH peak': d.batch_read_peak_kb,
    };
    const officialGet = d.official_get_peak_kb ?? d.c_get_peak_kb;
    const officialBatch = d.official_batch_read_peak_kb ?? d.c_batch_read_peak_kb;
    if (hasOfficial && officialGet != null) {
      entry['Official GET'] = officialGet;
    }
    if (hasOfficial && officialBatch != null) {
      entry['Official BATCH'] = officialBatch;
    }
    return entry;
  });

  return (
    <div className={chartStyles.chartWrap}>
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
          {hasOfficial && <Bar dataKey="Official GET" fill={COLOR_MEM_C_GET} />}
          {hasOfficial && <Bar dataKey="Official BATCH" fill={COLOR_MEM_C_BATCH} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
