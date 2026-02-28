import React from 'react';
import CollapsibleSection from './ui/CollapsibleSection';
import {DataTable} from './ui/DataTable';
import {LazyChart} from './ui/LazyChart';
import {fmtKb} from './helpers';
import tableStyles from './styles/Tables.module.css';
import dashStyles from './styles/BenchmarkDashboard.module.css';
import NumpyPanel from './NumpyPanel';
import type {FullBenchmarkData, ColorMode} from './types';

interface Props {
  data: FullBenchmarkData;
  colorMode: ColorMode;
}

function MemoryTable({data}: {data: FullBenchmarkData}) {
  const result = data.memory_profiling!;
  const hasOfficial = result.has_official ?? result.has_c;
  return (
    <DataTable>
      <thead>
        <tr>
          <th>Profile</th>
          <th>PUT peak</th>
          <th>GET peak</th>
          <th>BATCH peak</th>
          {hasOfficial && <th>Official GET</th>}
          {hasOfficial && <th>Official BATCH</th>}
        </tr>
      </thead>
      <tbody>
        {result.data.map((e) => (
          <tr key={e.label}>
            <td data-label="Profile">{e.label}</td>
            <td data-label="PUT peak" className={tableStyles.numCell}>{fmtKb(e.put_peak_kb)}</td>
            <td data-label="GET peak" className={tableStyles.numCell}>{fmtKb(e.get_peak_kb)}</td>
            <td data-label="BATCH peak" className={tableStyles.numCell}>{fmtKb(e.batch_read_peak_kb)}</td>
            {hasOfficial && <td data-label="Official GET" className={tableStyles.numCell}>{fmtKb(e.official_get_peak_kb ?? e.c_get_peak_kb)}</td>}
            {hasOfficial && <td data-label="Official BATCH" className={tableStyles.numCell}>{fmtKb(e.official_batch_read_peak_kb ?? e.c_batch_read_peak_kb)}</td>}
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

export default function MemoryPanel({data, colorMode}: Props) {
  return (
    <div>
      {/* Memory Profiling */}
      {data.memory_profiling && (
        <div className={dashStyles.scenarioCard}>
          <h3>Memory Profiling</h3>
          <p className={dashStyles.sectionDesc}>
            Peak memory per operation type across data sizes ({data.memory_profiling.count.toLocaleString()} ops).
            Measured via <code>tracemalloc</code>.
            {(data.memory_profiling.has_official ?? data.memory_profiling.has_c) && ' Includes official client comparison.'}
          </p>
          <LazyChart render={() => {
            const {MemoryProfileChart} = require('./charts/MemoryProfileChart');
            return <MemoryProfileChart result={data.memory_profiling} colorMode={colorMode} />;
          }} />
          <CollapsibleSection title="Memory Detail Table">
            <MemoryTable data={data} />
          </CollapsibleSection>
        </div>
      )}

      {/* NumPy Batch */}
      <NumpyPanel
        numpyData={data.numpy_batch ?? null}
        colorMode={colorMode}
      />
    </div>
  );
}
