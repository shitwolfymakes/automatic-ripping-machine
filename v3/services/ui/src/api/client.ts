// Thin fetch wrapper. JWT in localStorage, attached on every request; 401
// resets the auth store and the router redirects to /login. Same-origin
// requests by default since nginx proxies /api/* and /ws/*; override with
// VITE_API_BASE for `npm run dev` against a backend on a different port.

const TOKEN_KEY = 'arm_token'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

let on401: () => void = () => {}

export function setUnauthorizedHandler(fn: () => void): void {
  on401 = fn
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  expectJson = true,
): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (resp.status === 401) {
    on401()
    throw new ApiError(401, 'unauthorized', await safeJson(resp))
  }
  if (!resp.ok) {
    const data = await safeJson(resp)
    const detail =
      typeof data === 'object' &&
      data &&
      'detail' in data &&
      typeof (data as { detail: unknown }).detail === 'string'
        ? (data as { detail: string }).detail
        : `${method} ${path} failed`
    throw new ApiError(resp.status, detail, data)
  }
  if (!expectJson) return undefined as T
  return (await resp.json()) as T
}

async function safeJson(resp: Response): Promise<unknown> {
  try {
    return await resp.json()
  } catch {
    return null
  }
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: (path: string) => request<void>('DELETE', path, undefined, false),
}
