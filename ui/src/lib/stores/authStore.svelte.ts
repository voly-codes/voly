import {
  clearToken,
  fetchAuthStatus,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  setUnauthorizedHandler,
} from '../api/client.js'

let enabled = $state(false)
let user = $state<string | null>(null)
let ready = $state(false)
let loginOpen = $state(false)
let error = $state<string | null>(null)
let loading = $state(false)

/** Probe server auth mode and restore local token presence. */
async function init() {
  loading = true
  error = null
  try {
    const status = await fetchAuthStatus()
    enabled = Boolean(status?.enabled)
    if (enabled && getToken()) {
      // Token exists; username is not in JWT client-side without decode — mark session present.
      user = 'signed-in'
    } else if (!enabled) {
      user = null
    } else {
      user = null
      loginOpen = true
    }
  } catch (e) {
    // Auth status is public; failure usually means API down — leave open mode.
    enabled = false
    error = e instanceof Error ? e.message : String(e)
  } finally {
    ready = true
    loading = false
  }

  setUnauthorizedHandler((_status, detail) => {
    if (!enabled) return
    apiLogout()
    user = null
    error = detail || 'Session expired'
    loginOpen = true
  })
}

async function login(username: string, password: string) {
  loading = true
  error = null
  try {
    const data = await apiLogin(username, password)
    user = username || data?.username || 'signed-in'
    loginOpen = false
    return true
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
    return false
  } finally {
    loading = false
  }
}

function logout() {
  apiLogout()
  user = null
  error = null
  if (enabled) loginOpen = true
}

function openLogin() {
  loginOpen = true
  error = null
}

function closeLogin() {
  // Only allow closing when auth is off, or already signed in.
  if (!enabled || user) loginOpen = false
}

export const auth = {
  get enabled() { return enabled },
  get user() { return user },
  get ready() { return ready },
  get loginOpen() { return loginOpen },
  set loginOpen(v: boolean) { loginOpen = v },
  get error() { return error },
  get loading() { return loading },
  get signedIn() { return !enabled || Boolean(user && getToken()) },
  init,
  login,
  logout,
  openLogin,
  closeLogin,
}
