let shortcuts = []

export function registerShortcuts(map) {
  shortcuts.push(map)
  return () => {
    shortcuts = shortcuts.filter(m => m !== map)
  }
}

function isInputFocused() {
  const el = document.activeElement
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if (el.isContentEditable) return true
  return false
}

function handler(e) {
  for (const map of shortcuts) {
    const fn = map[`${e.key}-${e.metaKey || e.ctrlKey}-${e.shiftKey}-${e.altKey}`]
    if (fn) {
      const skipFocusCheck = fn._global
      if (!skipFocusCheck && isInputFocused()) continue
      e.preventDefault()
      fn()
      return
    }
  }
}

export function global(fn) {
  fn._global = true
  return fn
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handler)
}
