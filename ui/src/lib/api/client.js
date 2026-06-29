const BASE = ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function fetchTasks(limit = 100, agent = '', status = '') {
  const params = new URLSearchParams({ limit })
  if (agent) params.set('agent', agent)
  if (status) params.set('status', status)
  return get(`/api/tasks?${params}`)
}

export async function fetchTask(taskId) {
  return get(`/api/tasks/${taskId}`)
}

export async function fetchSummary() {
  return get('/api/tasks/stats/summary')
}

export async function fetchStatus() {
  return get('/api/status')
}
