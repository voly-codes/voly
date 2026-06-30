const BASE = ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res
}

// Tasks
export const fetchTasks = (limit = 100, agent = '', status = '') =>
  get(`/api/tasks?${new URLSearchParams({ limit, ...(agent && { agent }), ...(status && { status }) })}`)

export const fetchTask = id => get(`/api/tasks/${id}`)

export const fetchSummary = () => get('/api/tasks/stats/summary')

export const fetchStatus = () => get('/api/status')

// Run (SSE stream) — returns async generator
export async function* runTask(req) {
  const res = await post('/api/run', req)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { yield JSON.parse(line.slice(6)) } catch {}
      }
    }
  }
}

// Registry
export const fetchAgents = () => get('/api/registry/agents')
export const fetchModels = (executor = 'pipeline') =>
  get(`/api/registry/models?executor=${encodeURIComponent(executor)}`)
export const fetchSkills = (source = '', status = 'active') =>
  get(`/api/registry/skills?${new URLSearchParams({ source, status })}`)

// Marketplace
export const fetchInstalledSkills = () => get('/api/marketplace/skills/installed')

export const fetchMarketplaceSkills = (page = 1, limit = 24, agent = '') =>
  get(`/api/marketplace/skills?${new URLSearchParams({ page, limit, ...(agent && { agent }) })}`)

export const searchMarketplace = (q, limit = 20) =>
  get(`/api/marketplace/skills/search?${new URLSearchParams({ q, limit })}`)

export const installSkill = skill_id =>
  post(`/api/marketplace/skills/${encodeURIComponent(skill_id)}/install`, {}).then(r => r.json())

// CF
export const fetchCFWorkersStatus = () => get('/api/cf/workers/status')
export const fetchCFSpend = (days = 7) => get(`/api/cf/spend/summary?days=${days}`)

// DSPy
export const fetchDSPyStatus = () => get('/api/dspy/status')

// Gateway
export const fetchGatewayStatus = () => get('/api/gateway/status')

// SSE task stream
export function taskStream() {
  const url = `${BASE}/api/tasks/stream`
  const source = new EventSource(url)
  return source
}

// Telemetry
export const fetchTelemetry = (days = 30) => get(`/api/telemetry/summary?days=${days}`)
