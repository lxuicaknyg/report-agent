import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

const LS_KEY = 'report-agent:auth-v1'

export interface AuthUser {
  id: string
  username: string
  avatar?: string | null
}

interface AuthSnapshot {
  token: string | null
  user: AuthUser | null
  expiresAt: number | null
  loggedInAt: number | null
}

const DEFAULT_SNAPSHOT: AuthSnapshot = { token: null, user: null, expiresAt: null, loggedInAt: null }

function loadFromLS(): AuthSnapshot {
  if (typeof window === 'undefined') return DEFAULT_SNAPSHOT
  try {
    const raw = window.localStorage.getItem(LS_KEY)
    if (!raw) return DEFAULT_SNAPSHOT
    const parsed = JSON.parse(raw) as Partial<AuthSnapshot>
    return {
      token: parsed.token ?? null,
      user: parsed.user && typeof parsed.user === 'object' && parsed.user.id && parsed.user.username
        ? { id: String(parsed.user.id), username: String(parsed.user.username), avatar: parsed.user.avatar ?? null }
        : null,
      expiresAt: typeof parsed.expiresAt === 'number' ? parsed.expiresAt : null,
      loggedInAt: typeof parsed.loggedInAt === 'number' ? parsed.loggedInAt : null,
    }
  } catch {
    return DEFAULT_SNAPSHOT
  }
}

function persist(snap: AuthSnapshot) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(LS_KEY, JSON.stringify(snap))
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<AuthUser | null>(null)
  const expiresAt = ref<number | null>(null)
  const loggedInAt = ref<number | null>(null)
  let loaded = false

  const username = computed<string | null>(() => user.value?.username ?? null)
  const isTokenFresh = computed(() => {
    if (!expiresAt.value) return true
    return Date.now() < expiresAt.value
  })
  const isLoggedIn = computed(() => Boolean(token.value && user.value && isTokenFresh.value))

  async function ensureLoaded() {
    if (loaded) return
    const snap = loadFromLS()
    token.value = snap.token
    user.value = snap.user
    expiresAt.value = snap.expiresAt
    loggedInAt.value = snap.loggedInAt
    loaded = true
    if (token.value && !isTokenFresh.value) {
      logout()
    }
  }

  async function login(uname: string, _password: string) {
    const name = (uname || 'admin').trim() || 'admin'
    const newToken = `fake-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const fakeUser: AuthUser = { id: `local-${name}`, username: name, avatar: null }
    const expires = Date.now() + 1000 * 60 * 60 * 12
    token.value = newToken
    user.value = fakeUser
    expiresAt.value = expires
    loggedInAt.value = Date.now()
    loaded = true
    persist({
      token: newToken,
      user: fakeUser,
      expiresAt: expires,
      loggedInAt: loggedInAt.value,
    })
    return true
  }

  function setJwtAuth(nextToken: string, nextUser: AuthUser, nextExpiresAt?: number | null) {
    token.value = nextToken
    user.value = nextUser
    expiresAt.value = nextExpiresAt ?? null
    loggedInAt.value = Date.now()
    loaded = true
    persist({
      token: nextToken,
      user: nextUser,
      expiresAt: nextExpiresAt ?? null,
      loggedInAt: loggedInAt.value,
    })
  }

  function logout() {
    token.value = null
    user.value = null
    expiresAt.value = null
    loggedInAt.value = null
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(LS_KEY)
    }
  }

  function $reset() {
    logout()
    loaded = false
  }

  return {
    token,
    user,
    username,
    expiresAt,
    loggedInAt,
    isLoggedIn,
    ensureLoaded,
    login,
    setJwtAuth,
    logout,
    $reset,
  }
})
