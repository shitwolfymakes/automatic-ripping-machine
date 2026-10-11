import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';
import { hydrateConfig } from '$lib/stores/config';
import { getToken } from '$lib/api/client';

export const prerender = false;
export const ssr = false;

// Once setup is confirmed complete, stop checking on every navigation.
// Only a hard page refresh (F5) resets this, which is the correct behavior
// since completing setup or clearing the DB are deliberate actions.
let setupConfirmedComplete = false;

// Hydrate feature flags once per page load.
let configHydrated = false;

// Anonymous (tokenless) requests act as the guest backend-side. With guest
// access off every one of them 401s, so the shell must not mount and start its
// pollers just to be bounced to /login. Once an anonymous probe succeeds, guest
// access is known to be on for this page load.
let guestAccessConfirmed = false;

// False only when the backend says an anonymous visitor is not allowed in. An
// unreachable or erroring backend counts as allowed, like the setup check below:
// the normal UI shows the outage. Raw fetch, not the API client, whose 401
// handler must not fire for a probe.
async function anonymousVisitAllowed(fetchFn: typeof fetch): Promise<boolean> {
	if (guestAccessConfirmed || getToken() !== null) return true;
	try {
		const resp = await fetchFn('/api/system/version');
		if (resp.status === 401) return false;
		guestAccessConfirmed = resp.ok;
	} catch {
		// ARM unreachable - let the normal UI handle it
	}
	return true;
}

function isAdminSession(): boolean {
	try {
		return getToken() !== null && localStorage.getItem('arm_role') === 'admin';
	} catch {
		return false;
	}
}

export const load: LayoutLoad = async ({ url, fetch }) => {
	// The sign-in pages need neither the config nor a session.
	if (url.pathname.startsWith('/login') || url.pathname.startsWith('/change-password')) return {};

	if (!(await anonymousVisitAllowed(fetch))) redirect(307, '/login');

	if (!configHydrated) {
		await hydrateConfig();
		configHydrated = true;
	}

	// The walkthrough itself.
	if (url.pathname.startsWith('/setup')) return {};

	// Skip if we already know setup is done (cached from a previous navigation)
	if (setupConfirmedComplete) return {};

	// Only the admin runs setup; guests browse normally. "Finish later" is
	// server-wide: the status endpoint then reports first_run=false.
	if (!isAdminSession()) return {};

	try {
		const resp = await fetch('/api/setup/status');
		if (resp.ok) {
			const status = await resp.json();
			if (status.first_run === true) {
				redirect(307, '/setup');
			}
			// Setup is complete or deferred - cache this so we don't re-check on every click
			setupConfirmedComplete = true;
		}
		// Non-ok response (503, etc.) - ARM unreachable, don't redirect
	} catch (e) {
		// Re-throw SvelteKit redirects (they use throw internally)
		if (e && typeof e === 'object' && 'status' in e && 'location' in e) throw e;
		// ARM unreachable - don't redirect, let the normal UI handle it
	}

	return {};
};
