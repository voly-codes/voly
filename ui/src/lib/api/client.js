const BASE = import.meta.env.VITE_VOLY_API_BASE_URL ?? ''
const TOKEN_KEY = 'voly_access_token'

/** @type {((status: number, detail: string) => void) | null} */
let onUnauthorized = null

export function setUnauthorizedHandler(fn) {
  onUnauthorized = typeof fn === 'function' ? fn : null
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearToken() {
  setToken('')
}

function authHeaders(extra = {}) {
  const headers = { ...extra }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function parseError(res) {
  let detail = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
  } catch {
    /* not json */
  }
  if (res.status === 401) {
    onUnauthorized?.(res.status, detail)
  }
  const err = new Error(detail)
  err.status = res.status
  return err
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!res.ok) throw await parseError(res)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await parseError(res)
  return res
}

// Auth
export const fetchAuthStatus = () => get('/api/auth/status')

export async function login(username, password) {
  const res = await post('/api/auth/login', { username, password })
  const data = await res.json()
  if (data?.access_token) setToken(data.access_token)
  return data
}

export function logout() {
  clearToken()
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

export const fetchMarketplacePlugins = (status = 'active', limit = 50, offset = 0) =>
  get(`/api/marketplace/plugins?${new URLSearchParams({ status, limit, offset })}`)

export const publishMarketplacePlugins = plugins =>
  post('/api/marketplace/plugins/sync', { plugins }).then(r => r.json())

// CF
export const fetchCFWorkersStatus = () => get('/api/cf/workers/status')
export const fetchCFSpend = (days = 7) => get(`/api/cf/spend/summary?days=${days}`)

// DSPy
export const fetchDSPyStatus = () => get('/api/dspy/status')

// Gateway
export const fetchGatewayStatus = () => get('/api/gateway/status')

// SSE task stream (token via query — EventSource cannot set Authorization)
export function taskStream() {
  const token = getToken()
  const qs = token ? `?access_token=${encodeURIComponent(token)}` : ''
  const url = `${BASE}/api/tasks/stream${qs}`
  const source = new EventSource(url)
  return source
}

// Telemetry
export const fetchTelemetry = (days = 30) => get(`/api/telemetry/summary?days=${days}`)
export const fetchProviderHealth = () => get('/api/providers/health')
