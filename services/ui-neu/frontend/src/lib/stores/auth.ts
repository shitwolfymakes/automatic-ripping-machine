import { writable, derived } from 'svelte/store';
import { getToken, setToken, clearToken } from '$lib/api/client';
import type { LoginResult } from '$lib/api/auth';

const _isAuthenticated = writable<boolean>(false);
const _passwordMustChange = writable<boolean>(false);
const _role = writable<string | null>(null);

export const isAuthenticated = { subscribe: _isAuthenticated.subscribe };
export const passwordMustChange = { subscribe: _passwordMustChange.subscribe };
export const role = { subscribe: _role.subscribe };
export const isAdmin = derived(_role, (r) => r === 'admin');
export const isGuest = derived(_role, (r) => r === 'guest');

// Reflect any persisted token (and role) into the in-memory store (call on app start).
// NOTE: passwordMustChange is intentionally NOT restored here — only the token
// and role are persisted. After a reload the client-side forced-change redirect
// resets to false, but that is safe: the backend independently enforces the gate
// (require_jwt 403s every endpoint except /auth/password and /auth/logout while
// the user's password_must_change is true). The client flag is UX, not security.
export function initAuth(): void {
	_isAuthenticated.set(getToken() !== null);
	try {
		_role.set(localStorage.getItem('arm_role'));
	} catch {
		/* ignore */
	}
}

export function applyLogin(result: LoginResult): void {
	setToken(result.access_token);
	_isAuthenticated.set(true);
	_passwordMustChange.set(result.password_must_change);
	_role.set(result.role);
	try {
		localStorage.setItem('arm_role', result.role);
	} catch {
		/* ignore */
	}
}

// Local-only logout: drop the token + reset state together. This is the ONLY
// correct way to clear auth — calling client.clearToken() directly would leave
// isAuthenticated stale-true. The 401 handler and logout control both route
// through here (or via setUnauthorizedHandler(logoutLocal)).
export function logoutLocal(): void {
	clearToken();
	_isAuthenticated.set(false);
	_passwordMustChange.set(false);
	_role.set(null);
	try {
		localStorage.removeItem('arm_role');
	} catch {
		/* ignore */
	}
}

export function clearPasswordMustChange(): void {
	_passwordMustChange.set(false);
}
