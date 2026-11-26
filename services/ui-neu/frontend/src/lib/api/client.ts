// Single API client core. JWT in site storage (see safe-storage), attached on every request;
// a 401 fires the unauthorized handler (which redirects to /login), except
// on a request that checks credentials.
// Same-origin by default — nginx proxies /api/* to the v3 backend.

import { readStorage, removeStorage, writeStorage } from '$lib/utils/safe-storage';

const TOKEN_KEY = 'arm_token';

export function getToken(): string | null {
	return readStorage(TOKEN_KEY);
}

export function setToken(token: string): void {
	writeStorage(TOKEN_KEY, token);
}

export function clearToken(): void {
	removeStorage(TOKEN_KEY);
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

/** The message to show when a request fails: an ApiError's message (the
 * backend's 400 detail, or "API {status}: {statusText}"), or the network
 * message when the request never reached the server. */
export function saveErrorMessage(e: unknown): string {
	return e instanceof ApiError ? e.message : NETWORK_ERROR_MESSAGE;
}

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

/** Options for one request. */
export interface RequestOptions {
	/**
	 * The request submits credentials (sign in, change password), so a 401
	 * means they are wrong, not that the session expired: the unauthorized
	 * handler is left alone and the backend's detail is thrown.
	 */
	checksCredentials?: boolean;
}

/**
 * A response body's detail as a message: a string detail as-is, or a
 * Pydantic 422's list of {msg, loc, ...} error objects joined by their
 * `msg` strings. Null for any other shape.
 */
function detailMessage(body: unknown): string | null {
	const detail = (body as { detail?: unknown } | null)?.detail;
	if (typeof detail === 'string') return detail;
	if (!Array.isArray(detail)) return null;
	const msgs = detail
		.map((item) => (item as { msg?: unknown } | null)?.msg)
		.filter((msg): msg is string => typeof msg === 'string');
	return msgs.length > 0 ? msgs.join('; ') : null;
}

/** The ApiError for a failed response: its detail, else "API {status}: {statusText}". */
async function responseError(res: Response): Promise<ApiError> {
	let message = `API ${res.status}: ${res.statusText}`;
	let body: unknown = null;
	try {
		body = await res.json();
		message = detailMessage(body) ?? message;
	} catch {
		/* no/non-JSON body: use the default message */
	}
	return new ApiError(res.status, message, body);
}

async function handle<T>(res: Response, options: RequestOptions = {}): Promise<T> {
	if (res.status === 401 && !options.checksCredentials) on401();
	if (!res.ok) throw await responseError(res);
	try {
		return (await res.json()) as T;
	} catch {
		// Empty/204 responses have no JSON body.
		return undefined as T;
	}
}

export async function apiFetch<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
	const res = await fetch(path, { ...init, headers: authHeaders(init?.headers) });
	return handle<T>(res, options);
}

/** Like apiFetch, but also hands back the response headers (for paged
 *  endpoints that report their total in `X-Total-Count`). */
export async function apiFetchResponse<T>(path: string, init?: RequestInit): Promise<{ data: T; headers: Headers }> {
	const res = await fetch(path, { ...init, headers: authHeaders(init?.headers) });
	return { data: await handle<T>(res), headers: res.headers };
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

export function post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
	return apiFetch<T>(
		path,
		{
			method: 'POST',
			body: body !== undefined ? JSON.stringify(body) : undefined
		},
		options
	);
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
