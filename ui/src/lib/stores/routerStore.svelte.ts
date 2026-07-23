let current = $state<{ page: string; taskId: string | null }>({ page: 'tasks', taskId: null })

function parseHash(): void {
  const raw = typeof window !== 'undefined' ? window.location.hash : ''
  const path = raw.startsWith('#/') ? raw.slice(2) : ''
  const [page = 'tasks', taskId = null] = path.split('/')
  const valid = ['tasks', 'gateway', 'telemetry', 'dspy']
  current = { page: valid.includes(page) ? page : 'tasks', taskId: taskId || null }
}

function navigate(page: string, taskId: string | null = null): void {
  // Update state synchronously — setting location.hash alone only takes
  // effect once the browser's own 'hashchange' event fires and re-runs
  // parseHash(), which lands on the next tick. Any code reading router.taskId
  // in that gap (e.g. tasksStore's 2s live-run poll) would see the *previous*
  // task's id and could reselect onto it. Setting the hash below still keeps
  // the URL shareable/refreshable; hashchange re-parsing it afterward is a
  // harmless no-op since it already matches.
  current = { page, taskId }
  if (typeof window !== 'undefined') {
    window.location.hash = taskId ? `#/${page}/${taskId}` : `#/${page}`
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
