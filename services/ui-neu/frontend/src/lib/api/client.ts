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

let on401: () => void = () => {};

export function setUnauthorizedHandler(fn: () => void): void {
	on401 = fn;
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
		throw new Error('API 401: Unauthorized');
	}
	if (!res.ok) {
		let message = `API ${res.status}: ${res.statusText}`;
		try {
			const body = await res.json();
			if (body && body.detail) {
				message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
			}
		} catch {
			/* use default message */
		}
		throw new Error(message);
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
