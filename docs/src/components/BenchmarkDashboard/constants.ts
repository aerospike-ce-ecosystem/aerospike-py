export const OPERATIONS = ['put', 'get', 'operate', 'remove', 'batch_read', 'batch_read_numpy', 'batch_write', 'batch_write_numpy', 'query'] as const;

export const OP_LABELS: Record<string, string> = {
  put: 'PUT',
  get: 'GET',
  operate: 'OPERATE',
  remove: 'REMOVE',
  batch_read: 'BATCH_READ',
  batch_read_numpy: 'BATCH_READ_NUMPY',
  batch_write: 'BATCH_WRITE',
  batch_write_numpy: 'BATCH_WRITE_NUMPY',
  query: 'QUERY',
};

// numpy ops have no official equivalent; compare against their non-numpy counterparts
export const CROSS_OP_BASELINE: Record<string, string> = {
  batch_read_numpy: 'batch_read',
  batch_write_numpy: 'batch_write',
};

// ── Chart Colors (4-client) ─────────────────────────────────

export const COLOR_APY_SYNC = '#673ab7';       // purple
export const COLOR_OFFICIAL_SYNC = '#78909c';   // gray
export const COLOR_OFFICIAL_ASYNC = '#ff9800';  // orange
export const COLOR_APY_ASYNC = '#4caf50';       // green

export const COLOR_PUT_P50 = '#7e57c2';
export const COLOR_PUT_P99 = '#b39ddb';
export const COLOR_GET_P50 = '#43a047';
export const COLOR_GET_P99 = '#a5d6a7';
export const COLOR_MEM_PUT = '#ef5350';
export const COLOR_MEM_GET = '#42a5f5';
export const COLOR_MEM_BATCH = '#ab47bc';
export const COLOR_MEM_C_GET = '#78909c';
export const COLOR_MEM_C_BATCH = '#b0bec5';
export const COLOR_READ = '#4caf50';
export const COLOR_WRITE = '#f44336';
export const COLOR_THROUGHPUT = '#673ab7';

// NumPy chart colors
export const COLOR_DICT_SYNC = '#673ab7';
export const COLOR_NUMPY_SYNC = '#e91e63';
export const COLOR_DICT_ASYNC = '#4caf50';
export const COLOR_NUMPY_ASYNC = '#2196f3';
