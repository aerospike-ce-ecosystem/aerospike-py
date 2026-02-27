import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';

export function LazyChart({height = 400, render}: {height?: number; render: () => React.ReactElement}) {
  return (
    <BrowserOnly fallback={<div style={{height}}>Loading chart...</div>}>
      {render}
    </BrowserOnly>
  );
}
