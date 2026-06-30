let current = $state<{ page: string; taskId: string | null }>({ page: 'tasks', taskId: null })

function parseHash(): void {
  const raw = typeof window !== 'undefined' ? window.location.hash : ''
  const path = raw.startsWith('#/') ? raw.slice(2) : ''
  const [page = 'tasks', taskId = null] = path.split('/')
  const valid = ['tasks', 'gateway', 'telemetry', 'dspy']
  current = { page: valid.includes(page) ? page : 'tasks', taskId: taskId || null }
}

function navigate(page: string, taskId: string | null = null): void {
  const hash = taskId ? `#/${page}/${taskId}` : `#/${page}`
  if (typeof window !== 'undefined') {
    window.location.hash = hash
  } else {
    current = { page, taskId }
  }
}

function init(): void {
  parseHash()
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', parseHash)
  }
}

export const router = {
  get page() { return current.page },
  get taskId() { return current.taskId },
  init,
  navigate,
  parseHash,
}
