import React from 'react';
import type {ColorMode} from '../types';

export function themeColors(colorMode: ColorMode) {
  const isDark = colorMode === 'dark';
  return {
    text: isDark ? '#e0e0e0' : '#333333',
    grid: isDark ? '#444444' : '#cccccc',
    tooltipBg: isDark ? '#1e1e1e' : '#ffffff',
    tooltipBorder: isDark ? '#555555' : '#cccccc',
  };
}

export function ChartTooltip({
  active,
  payload,
  label,
  colorMode,
  unit,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{name: string; value: number; color: string}>;
  label?: string;
  colorMode: ColorMode;
  unit: string;
  formatter?: (name: string, value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const theme = themeColors(colorMode);

  const formatValue = (name: string, value: number): string => {
    if (formatter) return formatter(name, value);
    if (unit === 'ms') return `${value.toFixed(3)}ms`;
    if (unit === 'kb') return `${value.toLocaleString()} KB`;
    if (unit === 'pct') return `${value.toFixed(1)}%`;
    return `${value.toLocaleString()}/s`;
  };

  return (
    <div
      style={{
        background: theme.tooltipBg,
        border: `1px solid ${theme.tooltipBorder}`,
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 13,
      }}
    >
      <p style={{margin: 0, fontWeight: 600, color: theme.text}}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{margin: '4px 0 0', color: entry.color}}>
          {entry.name}: {formatValue(entry.name, entry.value)}
        </p>
      ))}
    </div>
  );
}

export function speedupLabel(target: number, baseline: number, lowerIsBetter: boolean): string | null {
  if (!target || !baseline) return null;
  const pct = lowerIsBetter
    ? ((baseline - target) / baseline) * 100
    : ((target - baseline) / baseline) * 100;
  if (pct > 0) return `${pct.toFixed(0)}%\u2191`;
  if (pct < 0) return `${Math.abs(pct).toFixed(0)}%\u2193`;
  return null;
}
