import {
  clearToken,
  fetchAuthStatus,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  setToken,
  setUnauthorizedHandler,
} from '../api/client.js'

let enabled = $state(false)
let provider = $state<'none' | 'local' | 'clerk'>('none')
let clerkPublishableKey = $state('')
let user = $state<string | null>(null)
let ready = $state(false)
let loginOpen = $state(false)
let error = $state<string | null>(null)
let loading = $state(false)

/** @type {import('@clerk/clerk-js').Clerk | null} */
let clerkInstance: any = null

async function loadClerk(publishableKey: string) {
  if (clerkInstance) return clerkInstance
  const { Clerk } = await import('@clerk/clerk-js')
  const clerk = new Clerk(publishableKey)
  await clerk.load()
  clerkInstance = clerk
  return clerk
}

async function syncClerkToken() {
  if (!clerkInstance?.session) {
    clearToken()
    user = null
    return
  }
  try {
    const token = await clerkInstance.session.getToken()
    if (token) {
      setToken(token)
      user =
        clerkInstance.user?.primaryEmailAddress?.emailAddress
        || clerkInstance.user?.username
        || clerkInstance.user?.id
        || 'signed-in'
    } else {
      clearToken()
      user = null
    }
  } catch {
    clearToken()
    user = null
  }
}

/** Probe server auth mode and restore session. */
async function init() {
  loading = true
  error = null
  try {
    const status = await fetchAuthStatus()
    enabled = Boolean(status?.enabled)
    provider = (status?.provider === 'clerk' || status?.mode === 'clerk')
      ? 'clerk'
      : (status?.enabled ? 'local' : 'none')
    clerkPublishableKey = status?.clerk?.publishable_key || ''

    if (provider === 'clerk' && clerkPublishableKey) {
      const clerk = await loadClerk(clerkPublishableKey)
      clerk.addListener?.(async () => {
        await syncClerkToken()
        if (!clerk.user && enabled) loginOpen = true
      })
      if (clerk.user) {
        await syncClerkToken()
        loginOpen = false
      } else {
        user = null
        loginOpen = true
      }
    } else if (enabled && getToken()) {
      user = 'signed-in'
      loginOpen = false
    } else if (enabled) {
      user = null
      loginOpen = true
    } else {
      user = null
      loginOpen = false
    }
  } catch (e) {
    enabled = false
    provider = 'none'
    error = e instanceof Error ? e.message : String(e)
  } finally {
    ready = true
    loading = false
  }

  setUnauthorizedHandler((_status, detail) => {
    if (!enabled) return
    if (provider === 'clerk') {
      clerkInstance?.signOut?.().catch(() => {})
    }
    apiLogout()
    user = null
    error = detail || 'Session expired'
    loginOpen = true
  })
}

async function login(username: string, password: string) {
  if (provider === 'clerk') {
    return openClerkSignIn()
  }
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

async function openClerkSignIn() {
  if (!clerkPublishableKey) {
    error = 'Clerk publishable key missing from /api/auth/status'
    return false
  }
  loading = true
  error = null
  try {
    const clerk = await loadClerk(clerkPublishableKey)
    // Mount Clerk's hosted sign-in into a dedicated node if present.
    const el = document.getElementById('clerk-sign-in')
    if (el) {
      clerk.mountSignIn(el)
    } else {
      await clerk.openSignIn({})
    }
    // Wait briefly for session after modal interaction is handled by listener
    if (clerk.user) {
      await syncClerkToken()
      loginOpen = false
      return true
    }
    return false
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
    return false
  } finally {
    loading = false
  }
}

async function logout() {
  if (provider === 'clerk' && clerkInstance) {
    try {
      await clerkInstance.signOut()
    } catch {
      /* ignore */
    }
  }
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
  if (!enabled || user) loginOpen = false
}

/** Refresh Clerk token (call before long SSE / sensitive ops if needed). */
async function refreshToken() {
  if (provider === 'clerk') await syncClerkToken()
}

export const auth = {
  get enabled() { return enabled },
  get provider() { return provider },
  get clerkPublishableKey() { return clerkPublishableKey },
  get user() { return user },
  get ready() { return ready },
  get loginOpen() { return loginOpen },
  set loginOpen(v: boolean) { loginOpen = v },
  get error() { return error },
  get loading() { return loading },
  get signedIn() { return !enabled || Boolean(user && getToken()) },
  init,
  login,
  openClerkSignIn,
  logout,
  openLogin,
  closeLogin,
  refreshToken,
}
