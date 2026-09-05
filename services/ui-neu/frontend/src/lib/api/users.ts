import type { UserView } from '$lib/types/api.gen';
import { get, post, patch } from './client';

export function fetchUsers(): Promise<UserView[]> {
	return get<UserView[]>('/api/users');
}

export function setUserDisabled(id: string, disabled: boolean): Promise<UserView> {
	return patch<UserView>(`/api/users/${id}`, { disabled });
}

export function setUserPassword(id: string, newPassword: string): Promise<unknown> {
	return post(`/api/users/${id}/password`, { new_password: newPassword });
}
