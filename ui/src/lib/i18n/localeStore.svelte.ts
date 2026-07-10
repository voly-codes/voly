/**
 * UI locale store — English default, Russian optional.
 * Persists to localStorage; drives document.documentElement.lang.
 */
import en from './en/index.js'
import ru from './ru/index.js'

export type Locale = 'en' | 'ru'

const STORAGE_KEY = 'voly-lang'
const catalogs: Record<Locale, Record<string, string | string[]>> = { en, ru }

function detect(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'ru') return stored
  } catch {
    /* ignore */
  }
  // Product default: English (not browser language)
  return 'en'
}

const initialLocale: Locale = typeof localStorage !== 'undefined' ? detect() : 'en'
let locale = $state<Locale>(initialLocale)

function syncDom(loc: Locale) {
  if (typeof document === 'undefined') return
  document.documentElement.lang = loc
  try {
    localStorage.setItem(STORAGE_KEY, loc)
  } catch {
    /* ignore */
  }
}

// Apply once at module load (before components mount — prevents FOUC)
syncDom(initialLocale)

/** Russian plural: [one, few, many] */
function pluralRu(n: number, forms: string[]): string {
  const abs = Math.abs(n) % 100
  const n1 = abs % 10
  if (abs > 10 && abs < 20) return forms[2] ?? forms[forms.length - 1]
  if (n1 > 1 && n1 < 5) return forms[1] ?? forms[0]
  if (n1 === 1) return forms[0]
  return forms[2] ?? forms[forms.length - 1]
}

function pluralEn(n: number, forms: string[]): string {
  return n === 1 ? forms[0] : (forms[1] ?? forms[0])
}

/**
 * Translate a key. Params: `{name}` interpolation; `n` for plurals.
 * Arrays in catalogs: EN [one, other], RU [one, few, many].
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const cat = catalogs[locale] ?? catalogs.en
  let raw: string | string[] = cat[key] ?? catalogs.en[key] ?? key

  if (Array.isArray(raw)) {
    const n = Number(params?.n ?? 0)
    raw = locale === 'ru' ? pluralRu(n, raw) : pluralEn(n, raw)
  }

  let s = String(raw)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      s = s.split(`{${k}}`).join(String(v))
    }
  }
  return s
}

export const i18n = {
  get locale(): Locale {
    return locale
  },
  set locale(v: Locale) {
    if (v !== 'en' && v !== 'ru') return
    locale = v
    syncDom(v)
  },
  t,
  set(v: Locale) {
    i18n.locale = v
  },
  toggle() {
    i18n.locale = locale === 'en' ? 'ru' : 'en'
  },
}
