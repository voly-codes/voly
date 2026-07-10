import { i18n, t } from '../i18n/localeStore.svelte.ts'

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

/** @deprecated use fmtDur */
export const fmtDuration = fmtDur

export function fmtRel(mtime) {
  void i18n.locale
  if (!mtime) return ''
  const d = new Date(mtime * 1000)
  const diff = (Date.now() - d) / 1000
  if (diff < 60) return t('time.justNow')
  if (diff < 3600) return t('time.minAgo', { n: Math.round(diff / 60) })
  if (diff < 86400) return t('time.hourAgo', { n: Math.round(diff / 3600) })
  const loc = t('time.dateLocale') || 'en'
  return d.toLocaleDateString(loc === 'ru' ? 'ru-RU' : 'en-US', {
    day: 'numeric',
    month: 'short',
  })
}

/** @deprecated use fmtRel */
export const fmtRelative = fmtRel

export function calcPct(saved, total) {
  if (!total || !saved) return null
  return Math.round((saved / (total + saved)) * 100)
}

/** Live map of status → label for current locale */
export function statusLabel(status) {
  void i18n.locale
  const key = `status.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

/**
 * Backward-compatible object used by existing components (`statusRu[status]`).
 * Rebuilt as a getter object so labels follow the active locale.
 */
export const statusRu = new Proxy(
  {},
  {
    get(_t, prop) {
      if (typeof prop !== 'string') return undefined
      return statusLabel(prop)
    },
  },
)

export function fmtCost(usd) {
  if (usd == null) return '—'
  if (usd === 0) return '$0'
  if (usd < 0.001) return `$${usd.toFixed(6)}`
  if (usd < 1) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}
