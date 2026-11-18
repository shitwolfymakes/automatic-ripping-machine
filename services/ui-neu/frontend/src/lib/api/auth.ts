import { post } from './client';

export interface LoginResult {
	access_token: string;
	expires_at: string;
	password_must_change: boolean;
	role: string;
}

export function login(username: string, password: string): Promise<LoginResult> {
	return post<LoginResult>('/api/auth/login', { username, password }, { checksCredentials: true });
}

export function logout(): Promise<unknown> {
	return post('/api/auth/logout');
}

/** A wrong current password is a 400; a 401 here means the token, so it ends the session like any other. */
export function changePassword(currentPassword: string, newPassword: string): Promise<unknown> {
	return post('/api/auth/password', { current_password: currentPassword, new_password: newPassword });
}
