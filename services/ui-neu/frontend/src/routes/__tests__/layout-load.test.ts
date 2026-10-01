// Unit tests for the +layout.ts `load` guard itself (not the +layout.svelte
// component — see layout-guest.test.ts for that). Tokenless requests are a
// valid browsing state (guest, backend-side) — the load guard no longer
// attempts any acquisition or redirect based on token presence; it only
// hydrates config and runs the first-run setup check.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { isRedirect } from '@sveltejs/kit';
import type { LayoutLoad } from '../$types';

const getTokenMock = vi.fn<() => string | null>(() => null);
vi.mock('$lib/api/client', () => ({
	getToken: () => getTokenMock()
}));

const hydrateConfigMock = vi.fn(() => Promise.resolve());
vi.mock('$lib/stores/config', () => ({
	hydrateConfig: () => hydrateConfigMock()
}));

function loadArgs(pathname: string, fetchImpl: typeof fetch = vi.fn()) {
	return {
		url: new URL(`http://localhost${pathname}`),
		fetch: fetchImpl
	} as unknown as Parameters<LayoutLoad>[0];
}

describe('+layout.ts load guard', () => {
	beforeEach(() => {
		vi.resetModules();
		getTokenMock.mockReset();
		getTokenMock.mockReturnValue(null);
		hydrateConfigMock.mockClear();
		localStorage.clear();
		sessionStorage.clear();
	});

	it('no token + non-auth route: hydrates config and does not redirect', async () => {
		const { load } = await import('../+layout');
		const result = await load(loadArgs('/'));

		expect(hydrateConfigMock).toHaveBeenCalledTimes(1);
		expect(result).toEqual({});
	});

	it('token present: behaves the same as no token (no redirect)', async () => {
		getTokenMock.mockReturnValue('existing-token');

		const { load } = await import('../+layout');
		const result = await load(loadArgs('/'));

		expect(result).toEqual({});
	});

	it('auth route (/login) + no token: no redirect', async () => {
		const { load } = await import('../+layout');
		const result = await load(loadArgs('/login'));

		expect(result).toEqual({});
	});

	function statusFetch(body: unknown, ok = true) {
		return vi.fn(() => Promise.resolve({ ok, json: () => Promise.resolve(body) })) as unknown as typeof fetch;
	}
	function asAdmin() {
		getTokenMock.mockReturnValue('tok');
		localStorage.setItem('arm_role', 'admin');
	}

	it('admin + first run redirects to /setup', async () => {
		asAdmin();
		const { load } = await import('../+layout');
		let caught: unknown;
		try {
			await load(loadArgs('/', statusFetch({ first_run: true })));
		} catch (e) {
			caught = e;
		}
		expect(isRedirect(caught)).toBe(true);
		expect((caught as { location: string }).location).toBe('/setup');
	});

	it('guests and anonymous visitors are never sent to /setup', async () => {
		const fetchImpl = statusFetch({ first_run: true });
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/', fetchImpl))).toEqual({});
		expect(fetchImpl).not.toHaveBeenCalled();
	});

	it('Finish later pauses the redirect for the browser session', async () => {
		asAdmin();
		sessionStorage.setItem('arm_setup_finish_later', '1');
		const fetchImpl = statusFetch({ first_run: true });
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/', fetchImpl))).toEqual({});
		expect(fetchImpl).not.toHaveBeenCalled();
	});

	it('an unreachable backend never redirects', async () => {
		asAdmin();
		const fetchImpl = vi.fn(() => Promise.reject(new Error('down'))) as unknown as typeof fetch;
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/', fetchImpl))).toEqual({});
	});

	it('caches a completed setup so later navigations skip the check', async () => {
		asAdmin();
		const fetchImpl = statusFetch({ first_run: false });
		const { load } = await import('../+layout');
		await load(loadArgs('/', fetchImpl));
		await load(loadArgs('/jobs', fetchImpl));
		expect(fetchImpl).toHaveBeenCalledTimes(1);
	});

	it('the walkthrough and sign-in pages never check', async () => {
		asAdmin();
		const fetchImpl = statusFetch({ first_run: true });
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/setup/drives', fetchImpl))).toEqual({});
		expect(await load(loadArgs('/change-password', fetchImpl))).toEqual({});
		expect(fetchImpl).not.toHaveBeenCalled();
	});
});
