import { post } from './client';

export interface LoginResult {
	access_token: string;
	expires_at: string;
	password_must_change: boolean;
	role: string;
}

export function login(username: string, password: string): Promise<LoginResult> {
	return post<LoginResult>('/api/auth/login', { username, password });
}

/**
 * @deprecated The backend's /api/auth/guest endpoint is removed — anonymous
 * (tokenless) requests now act as the guest implicitly. This stub remains
 * only because +layout.svelte / +layout.ts still call it; Task 4 removes
 * those callers, at which point this export should be deleted entirely.
 */
export function guestLogin(): Promise<LoginResult> {
	return Promise.reject(new Error('removed'));
}

export function logout(): Promise<unknown> {
	return post('/api/auth/logout');
}

export function changePassword(currentPassword: string, newPassword: string): Promise<unknown> {
	return post('/api/auth/password', { current_password: currentPassword, new_password: newPassword });
}
