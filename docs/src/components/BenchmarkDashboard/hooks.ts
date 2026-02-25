import {useState, useEffect, useCallback} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import type {FullBenchmarkData, ClientSection, NumpyBenchmarkData} from './types';

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

/** Migrate legacy "scan" keys to "query" across the whole report. */
function migrateData(d: FullBenchmarkData): FullBenchmarkData {
  return {
    ...d,
    rust_sync: migrateSection(d.rust_sync) ?? {},
    c_sync: migrateSection(d.c_sync) ?? null,
    rust_async: migrateSection(d.rust_async) ?? {},
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
      .then((d: FullBenchmarkData) => {
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

interface UseNumpyDataReturn {
  dates: ReportEntry[];
  selectedDate: string | null;
  setSelectedDate: (date: string) => void;
  data: NumpyBenchmarkData | null;
  loading: boolean;
  error: string | null;
}

export function useNumpyData(): UseNumpyDataReturn {
  const [dates, setDates] = useState<ReportEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [data, setData] = useState<NumpyBenchmarkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, NumpyBenchmarkData>>({});

  const baseUrl = useBaseUrl('/benchmark/numpy-results/');

  // Load index.json once
  useEffect(() => {
    fetch(`${baseUrl}index.json`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load numpy index.json (${res.status})`);
        return res.json();
      })
      .then((index: IndexData) => {
        if (!index.reports.length) throw new Error('No numpy reports available');
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
        if (!res.ok) throw new Error(`Failed to load numpy report (${res.status})`);
        return res.json();
      })
      .then((d: NumpyBenchmarkData) => {
        setCache((prev) => ({...prev, [selectedDate]: d}));
        setData(d);
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
