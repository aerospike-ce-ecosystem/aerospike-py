import React from 'react';
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';
import {useColorMode} from '@docusaurus/theme-common';
import HeroBanner from './HeroBanner';
import OverviewPanel from './OverviewPanel';
import LatencyThroughputPanel from './LatencyThroughputPanel';
import StabilityTailPanel from './StabilityTailPanel';
import AdvancedPanel from './AdvancedPanel';
import NumpyPanel from './NumpyPanel';
import {useBenchmarkData, useNumpyData} from './hooks';
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
  const {
    dates: numpyDates,
    selectedDate: numpySelectedDate,
    setSelectedDate: setNumpySelectedDate,
    data: numpyData,
    error: numpyError,
  } = useNumpyData();
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

  const hasBasic = data.rust_sync && Object.keys(data.rust_sync).length > 0;
  const hasAdvanced = data.data_size || data.concurrency_scaling || data.memory_profiling || data.mixed_workload;

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

          {hasBasic && (
            <TabItem value="stability-tail" label="Stability & Tail">
              <div className={styles.panelContent}>
                <StabilityTailPanel data={data} colorMode={colorMode} />
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
                numpyData={numpyData}
                numpyError={numpyError}
                numpyDates={numpyDates}
                numpySelectedDate={numpySelectedDate}
                onNumpyDateChange={setNumpySelectedDate}
                colorMode={colorMode}
              />
            </div>
          </TabItem>
        </Tabs>
      </div>
    </div>
  );
}
