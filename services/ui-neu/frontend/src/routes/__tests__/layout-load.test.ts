// Unit tests for the +layout.ts `load` guard itself (not the +layout.svelte
// component — see layout-guest.test.ts for that). Tokenless requests are a
// valid browsing state (guest, backend-side) — the load guard does not acquire
// a session; it probes once whether anonymous visits are allowed (sending the
// rest to /login), hydrates config and runs the first-run setup check.
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

	function versionFetch(status: number) {
		return vi.fn(() => Promise.resolve({ ok: status === 200, status })) as unknown as typeof fetch;
	}

	it('no token + guest access off: one probe, then /login, with no config or poller fan-out', async () => {
		const fetchImpl = versionFetch(401);
		const { load } = await import('../+layout');
		let caught: unknown;
		try {
			await load(loadArgs('/jobs', fetchImpl));
		} catch (e) {
			caught = e;
		}
		expect(isRedirect(caught)).toBe(true);
		expect((caught as { location: string }).location).toBe('/login');
		expect(fetchImpl).toHaveBeenCalledTimes(1);
		expect(fetchImpl).toHaveBeenCalledWith('/api/system/version');
		expect(hydrateConfigMock).not.toHaveBeenCalled();
	});

	it('no token + guest access on: loads normally and probes only once per page load', async () => {
		const fetchImpl = versionFetch(200);
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/', fetchImpl))).toEqual({});
		expect(await load(loadArgs('/jobs', fetchImpl))).toEqual({});
		expect(fetchImpl).toHaveBeenCalledTimes(1);
		expect(hydrateConfigMock).toHaveBeenCalledTimes(1);
	});

	it('a failing probe does not lock anyone out', async () => {
		const down = vi.fn(() => Promise.reject(new Error('down'))) as unknown as typeof fetch;
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/', down))).toEqual({});
		expect(hydrateConfigMock).toHaveBeenCalledTimes(1);
	});

	it('sign-in pages neither probe nor hydrate config', async () => {
		const fetchImpl = versionFetch(401);
		const { load } = await import('../+layout');
		expect(await load(loadArgs('/login', fetchImpl))).toEqual({});
		expect(await load(loadArgs('/change-password', fetchImpl))).toEqual({});
		expect(fetchImpl).not.toHaveBeenCalled();
		expect(hydrateConfigMock).not.toHaveBeenCalled();
	});

	it('token present: no probe, no redirect', async () => {
		getTokenMock.mockReturnValue('existing-token');
		const fetchImpl = vi.fn() as unknown as typeof fetch;

		const { load } = await import('../+layout');
		const result = await load(loadArgs('/', fetchImpl));

		expect(result).toEqual({});
		expect(fetchImpl).not.toHaveBeenCalled();
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
		expect(fetchImpl).not.toHaveBeenCalledWith('/api/setup/status');
	});

	it('the server decides: an old browser-session Finish later flag no longer pauses the redirect', async () => {
		// Finish later is recorded server-wide now (the status endpoint then
		// reports first_run=false for everyone); a leftover flag from an older
		// build must not hide a setup the server says is still pending.
		asAdmin();
		sessionStorage.setItem('arm_setup_finish_later', '1');
		const fetchImpl = statusFetch({ first_run: true });
		const { load } = await import('../+layout');
		let caught: unknown;
		try {
			await load(loadArgs('/', fetchImpl));
		} catch (e) {
			caught = e;
		}
		expect(isRedirect(caught)).toBe(true);
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
