import { redirect } from '@sveltejs/kit';
import { getToken } from '$lib/api/client';
import { persistedRole } from '$lib/stores/auth';

export const prerender = false;
export const ssr = false;

// The walkthrough is the admin's: sign in first; guests go to the dashboard.
export function load() {
	if (!getToken()) redirect(307, '/login');
	if (persistedRole() !== 'admin') redirect(307, '/');
	return {};
}
