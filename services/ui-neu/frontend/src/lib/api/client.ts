// Single API client core. JWT in localStorage, attached on every request;
// a 401 fires the unauthorized handler (wired in Tier B to redirect to /login).
// Same-origin by default — nginx proxies /api/* to the v3 backend.

const TOKEN_KEY = 'arm_token';

export function getToken(): string | null {
	return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
	localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
	localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
	status: number;
	body: unknown;
	constructor(status: number, message: string, body: unknown) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.body = body;
	}
}

// Shown when a request never reaches the server (fetch itself throws - the
// network is down, TLS failed, and so on) rather than the server answering
// with a non-2xx status. Kept here (a plain .ts module, not a .svelte
// <script> block) rather than inline at the call site: the straight
// apostrophe in "didn't" is indistinguishable from a string delimiter to
// ui-neu-style-lint's script-literal scan, which would otherwise mis-pair
// quotes for the rest of that file and flag unrelated code past it.
export const NETWORK_ERROR_MESSAGE = "The server didn't respond. Your changes are still here, so try Save again.";

let on401: () => void = () => {};

export function setUnauthorizedHandler(fn: () => void): void {
	on401 = fn;
}

/** Invoke the registered unauthorized handler — for raw-fetch callers (e.g.
 *  NDJSON endpoints) that bypass apiFetch but must still trigger session expiry. */
export function notifyUnauthorized(): void {
	on401();
}

function authHeaders(extra?: HeadersInit): Record<string, string> {
	const headers: Record<string, string> = { 'Content-Type': 'application/json' };
	const token = getToken();
	if (token) headers['Authorization'] = `Bearer ${token}`;
	return { ...headers, ...(extra as Record<string, string> | undefined) };
}

async function handle<T>(res: Response): Promise<T> {
	if (res.status === 401) {
		on401();
		let body: unknown = null;
		try {
			body = await res.json();
		} catch {
			/* no/non-JSON body */
		}
		throw new ApiError(401, 'API 401: Unauthorized', body);
	}
	if (!res.ok) {
		let message = `API ${res.status}: ${res.statusText}`;
		let body: unknown = null;
		try {
			body = await res.json();
			// A string detail becomes the message as-is; a Pydantic 422's detail is
			// instead a list of {msg, loc, ...} error objects, so join their `msg`
			// strings into one readable message. Any other shape keeps the
			// status-text default, and the full body is always on .body.
			const detail = (body as { detail?: unknown } | null)?.detail;
			if (typeof detail === 'string') {
				message = detail;
			} else if (Array.isArray(detail) && detail.length > 0) {
				const msgs = detail
					.map((item) => (item as { msg?: unknown } | null)?.msg)
					.filter((msg): msg is string => typeof msg === 'string');
				if (msgs.length > 0) {
					message = msgs.join('; ');
				}
			}
		} catch {
			/* use default message */
		}
		throw new ApiError(res.status, message, body);
	}
	try {
		return (await res.json()) as T;
	} catch {
		// Empty/204 responses have no JSON body.
		return undefined as T;
	}
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, { ...init, headers: authHeaders(init?.headers) });
	return handle<T>(res);
}

export async function apiFormPost<T>(path: string, formData: FormData): Promise<T> {
	// FormData sets its own multipart Content-Type; only attach auth.
	const headers: Record<string, string> = {};
	const token = getToken();
	if (token) headers['Authorization'] = `Bearer ${token}`;
	const res = await fetch(path, { method: 'POST', body: formData, headers });
	return handle<T>(res);
}

export function get<T>(path: string): Promise<T> {
	return apiFetch<T>(path, { method: 'GET' });
}

export function post<T>(path: string, body?: unknown): Promise<T> {
	return apiFetch<T>(path, {
		method: 'POST',
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
}

export function patch<T>(path: string, body?: unknown): Promise<T> {
	return apiFetch<T>(path, {
		method: 'PATCH',
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
}

export function put<T>(path: string, body?: unknown): Promise<T> {
	return apiFetch<T>(path, {
		method: 'PUT',
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
}

export function del<T = void>(path: string): Promise<T> {
	return apiFetch<T>(path, { method: 'DELETE' });
}

export function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
	const parts: string[] = [];
	for (const [k, v] of Object.entries(params)) {
		if (v !== undefined && v !== null) {
			parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
		}
	}
	return parts.length ? `?${parts.join('&')}` : '';
}
