const RELATIVE_UNITS = [
  ['ano', 31536000],
  ['mês', 2592000],
  ['dia', 86400],
  ['hora', 3600],
  ['min', 60],
];

export function relativeTime(isoString) {
  if (!isoString) return 'nunca';

  const seconds = Math.max(0, (Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 45) return 'agora';

  for (const [unit, size] of RELATIVE_UNITS) {
    if (seconds >= size) {
      const value = Math.floor(seconds / size);
      const plural = value > 1 ? (unit === 'mês' ? 'meses' : `${unit}s`) : unit;
      return `há ${value} ${plural}`;
    }
  }
  return `há ${Math.floor(seconds)}s`;
}

export function duration(ms) {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function statusLabel(status) {
  const labels = {
    REGISTERED: 'Registered',
    STOPPED: 'Stopped',
    STARTING: 'Starting',
    RUNNING: 'Running',
    ERROR: 'Error',
    UNKNOWN: 'Unknown',
    MISSING: 'Missing',
  };
  return labels[status] ?? status;
}

export function folderName(path) {
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
