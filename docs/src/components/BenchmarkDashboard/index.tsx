import React from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import {useColorMode} from '@docusaurus/theme-common';
import HeroBanner from './HeroBanner';
import OverviewPanel from './OverviewPanel';
import LatencyThroughputPanel from './LatencyThroughputPanel';
import AdvancedPanel from './AdvancedPanel';
import NumpyPanel from './NumpyPanel';
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

  const hasBasic = data.aerospike_py_sync && Object.keys(data.aerospike_py_sync).length > 0;
  const hasAdvanced = data.data_size || data.concurrency_scaling || data.memory_profiling || data.mixed_workload;
  const hasNumpy = !!data.numpy_batch;

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
          <TabItem value="overview" label="Overview" default>
            <div className={styles.panelContent}>
              <OverviewPanel data={data} colorMode={colorMode} />
            </div>
          </TabItem>

          {hasBasic && (
            <TabItem value="latency-throughput" label="Latency & Throughput">
              <div className={styles.panelContent}>
                <LatencyThroughputPanel data={data} colorMode={colorMode} />
              </div>
            </TabItem>
          )}

          {hasAdvanced && (
            <TabItem value="advanced" label="Advanced Profiling">
              <div className={styles.panelContent}>
                <AdvancedPanel data={data} colorMode={colorMode} />
              </div>
            </TabItem>
          )}

          <TabItem value="numpy" label="NumPy Batch">
            <div className={styles.panelContent}>
              <NumpyPanel
                numpyData={hasNumpy ? data.numpy_batch! : null}
                colorMode={colorMode}
              />
            </div>
          </TabItem>
        </Tabs>
      </div>
    </div>
  );
}
