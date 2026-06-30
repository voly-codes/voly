const STORAGE_KEY = 'codeops-theme'

let dark = $state(loadTheme())

function loadTheme(): boolean {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'dark') return true
    if (stored === 'light') return false
  }
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return true
  }
  return false
}

function sync() {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', dark)
  localStorage?.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
}

// Apply on module load (before components mount — prevents FOUC)
sync()

export const theme = {
  get dark() { return dark },
  set dark(v: boolean) { dark = v; sync() },
  toggle() {
    dark = !dark
    sync()
  },
}
