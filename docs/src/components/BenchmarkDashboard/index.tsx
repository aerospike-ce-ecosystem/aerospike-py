import React from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import {useColorMode} from '@docusaurus/theme-common';
import HeroBanner from './HeroBanner';
import LatencyPanel from './LatencyPanel';
import MemoryPanel from './MemoryPanel';
import ConcurrencyPanel from './ConcurrencyPanel';
import {useBenchmarkData} from './hooks';
import styles from './styles/BenchmarkDashboard.module.css';

export default function BenchmarkDashboard(): React.ReactElement {
  const {
    dates,
    selectedDate,
    setSelectedDate,
    data,
    loading,
    error,
  } = useBenchmarkData();
  const {colorMode} = useColorMode();

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.errorBox}>
          <strong>Failed to load benchmark data.</strong>
          <p>Run <code>make run-benchmark-report</code> to generate benchmark data.</p>
          <details><summary>Error details</summary><pre>{error}</pre></details>
        </div>
      </div>
    );
  }

  if (!data || loading) {
    return <div className={styles.container}>Loading benchmark data...</div>;
  }

  const hasLatency = data.aerospike_py_sync && Object.keys(data.aerospike_py_sync).length > 0;
  const hasMemory = !!data.memory_profiling || !!data.numpy_batch;
  const hasConcurrency = !!data.high_concurrency_scaling || !!data.mixed_workload;

  return (
    <div className={styles.container}>
      {/* Hero Banner */}
      <HeroBanner
        data={data}
        dates={dates}
        selectedDate={selectedDate}
        onDateChange={setSelectedDate}
      />

      {/* Section Tabs */}
      <div className={styles.sectionTabs}>
        <Tabs groupId="benchmark-section">
          <TabItem value="latency" label="Latency & Throughput" default>
            <div className={styles.panelContent}>
              <LatencyPanel data={data} colorMode={colorMode} />
            </div>
          </TabItem>

          {hasMemory && (
            <TabItem value="memory" label="Memory Efficient">
              <div className={styles.panelContent}>
                <MemoryPanel data={data} colorMode={colorMode} />
              </div>
            </TabItem>
          )}

          {hasConcurrency && (
            <TabItem value="concurrency" label="Concurrency Efficient">
              <div className={styles.panelContent}>
                <ConcurrencyPanel data={data} colorMode={colorMode} />
              </div>
            </TabItem>
          )}
        </Tabs>
      </div>
    </div>
  );
}
