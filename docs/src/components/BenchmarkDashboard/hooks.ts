import {useState, useEffect, useCallback} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import type {FullBenchmarkData, ClientSection} from './types';

export interface ReportEntry {
  date: string;
  file: string;
}

interface IndexData {
  reports: ReportEntry[];
}

/** Rename legacy "scan" key to "query" in a ClientSection. */
function migrateSection(section: ClientSection | null): ClientSection | null {
  if (!section || !section.scan) return section;
  const {scan, ...rest} = section;
  return {...rest, query: scan};
}

/** Migrate legacy field names and "scan" keys to current schema. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function migrateData(d: any): FullBenchmarkData {
  const raw = d as Record<string, unknown>;

  // Legacy field name fallback: rust_sync → aerospike_py_sync, c_sync → official_sync, rust_async → aerospike_py_async
  const apySync = (raw.aerospike_py_sync ?? raw.rust_sync ?? {}) as ClientSection;
  const officialSync = (raw.official_sync ?? raw.c_sync ?? null) as ClientSection | null;
  const apyAsync = (raw.aerospike_py_async ?? raw.rust_async ?? {}) as ClientSection;
  const officialAsync = (raw.official_async ?? null) as ClientSection | null;

  // Migrate legacy memory_profiling fields
  const memoryProfiling = raw.memory_profiling as Record<string, unknown> | undefined;
  if (memoryProfiling) {
    const hasOfficial = !!(memoryProfiling.has_official ?? memoryProfiling.has_c);
    memoryProfiling.has_official = hasOfficial;
    const memData = memoryProfiling.data as Array<Record<string, unknown>> | undefined;
    if (memData) {
      for (const entry of memData) {
        if (entry.official_get_peak_kb == null && entry.c_get_peak_kb != null) {
          entry.official_get_peak_kb = entry.c_get_peak_kb;
        }
        if (entry.official_batch_read_peak_kb == null && entry.c_batch_read_peak_kb != null) {
          entry.official_batch_read_peak_kb = entry.c_batch_read_peak_kb;
        }
      }
    }
  }

  return {
    ...(d as unknown as FullBenchmarkData),
    aerospike_py_sync: migrateSection(apySync) ?? {},
    official_sync: migrateSection(officialSync) ?? null,
    aerospike_py_async: migrateSection(apyAsync) ?? {},
    official_async: migrateSection(officialAsync) ?? null,
  };
}

interface UseBenchmarkDataReturn {
  dates: ReportEntry[];
  selectedDate: string | null;
  setSelectedDate: (date: string) => void;
  data: FullBenchmarkData | null;
  loading: boolean;
  error: string | null;
}

export function useBenchmarkData(): UseBenchmarkDataReturn {
  const [dates, setDates] = useState<ReportEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [data, setData] = useState<FullBenchmarkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, FullBenchmarkData>>({});

  const baseUrl = useBaseUrl('/benchmark/results/');

  // Load index.json once
  useEffect(() => {
    fetch(`${baseUrl}index.json`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load index.json (${res.status})`);
        return res.json();
      })
      .then((index: IndexData) => {
        if (!index.reports.length) throw new Error('No benchmark reports available');
        setDates(index.reports);
        setSelectedDate(index.reports[0].date);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [baseUrl]);

  // Load report when selectedDate changes
  useEffect(() => {
    if (!selectedDate || !dates.length) return;

    // Check cache
    if (cache[selectedDate]) {
      setData(cache[selectedDate]);
      setLoading(false);
      return;
    }

    const entry = dates.find((d) => d.date === selectedDate);
    if (!entry) return;

    setLoading(true);
    fetch(`${baseUrl}${entry.file}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load report (${res.status})`);
        return res.json();
      })
      .then((d: unknown) => {
        const migrated = migrateData(d);
        setCache((prev) => ({...prev, [selectedDate]: migrated}));
        setData(migrated);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [selectedDate, dates, baseUrl, cache]);

  const handleSetDate = useCallback((date: string) => {
    setSelectedDate(date);
  }, []);

  return {dates, selectedDate, setSelectedDate: handleSetDate, data, loading, error};
}
