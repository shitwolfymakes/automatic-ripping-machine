import { redirect } from '@sveltejs/kit';
import { getToken } from '$lib/api/client';

export const prerender = false;
export const ssr = false;

function storedRole(): string | null {
	try {
		return localStorage.getItem('arm_role');
	} catch {
		return null;
	}
}

// The walkthrough is the admin's: sign in first; guests go to the dashboard.
export function load() {
	if (!getToken()) redirect(307, '/login');
	if (storedRole() !== 'admin') redirect(307, '/');
	return {};
}
