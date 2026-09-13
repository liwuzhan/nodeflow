export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export function formatDate(ts: number | string | null): string {
  if (!ts) return '—'
  const d = new Date(typeof ts === 'string' ? ts : ts * 1000)
  return d.toLocaleString('zh-CN')
}

export function formatArea(ha: number): string {
  if (ha >= 1) return `${ha.toFixed(2)} ha`
  return `${(ha * 10000).toFixed(0)} m²`
}
