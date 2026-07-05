export function fmtTokens(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

export function fmtDur(ms) {
  if (!ms) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtRel(mtime) {
  if (!mtime) return ''
  const d = new Date(mtime * 1000)
  const diff = (Date.now() - d) / 1000
  if (diff < 60) return 'только что'
  if (diff < 3600) return `${Math.round(diff / 60)}м назад`
  if (diff < 86400) return `${Math.round(diff / 3600)}ч назад`
  return d.toLocaleDateString('ru')
}

export function calcPct(saved, total) {
  if (!total || !saved) return null
  return Math.round((saved / (total + saved)) * 100)
}

export const statusRu = {
  completed: 'выполнено', failed: 'ошибка', running: 'в работе', error: 'ошибка',
}
