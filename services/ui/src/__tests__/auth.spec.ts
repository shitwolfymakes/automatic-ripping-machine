import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('hydrate picks up an existing token from localStorage', () => {
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    const auth = useAuthStore()
    auth.hydrate()
    expect(auth.token).toBe('aaa.bbb.ccc')
    expect(auth.isAuthenticated).toBe(true)
  })

  it('login stores the token and surfaces password_must_change', async () => {
    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'aaa.bbb.ccc',
          expires_at: '2030-01-01T00:00:00Z',
          password_must_change: true,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fakeFetch)

    const auth = useAuthStore()
    auth.hydrate()
    const resp = await auth.login({ username: 'admin', password: 'x' })
    expect(resp.password_must_change).toBe(true)
    expect(auth.token).toBe('aaa.bbb.ccc')
    expect(auth.passwordMustChange).toBe(true)
    expect(localStorage.getItem('arm_token')).toBe('aaa.bbb.ccc')
  })

  it('logout clears state and localStorage', async () => {
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    const auth = useAuthStore()
    auth.hydrate()

    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fakeFetch)

    await auth.logout()
    expect(auth.token).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('arm_token')).toBeNull()
  })

  it('a 401 response anywhere triggers reset', async () => {
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    const auth = useAuthStore()
    auth.hydrate()

    const fakeFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'expired' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fakeFetch)

    const { api } = await import('../api/client')
    await expect(api.get('/api/jobs')).rejects.toThrow()

    expect(auth.token).toBeNull()
  })
})
