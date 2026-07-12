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

export function guestLogin(): Promise<LoginResult> {
	return post<LoginResult>('/api/auth/guest');
}

export function logout(): Promise<unknown> {
	return post('/api/auth/logout');
}

export function changePassword(currentPassword: string, newPassword: string): Promise<unknown> {
	return post('/api/auth/password', { current_password: currentPassword, new_password: newPassword });
}
