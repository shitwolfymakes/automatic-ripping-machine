import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import LoginPage from '../+page.svelte';

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({
	goto: (...args: unknown[]) => gotoMock(...args)
}));

vi.mock('$lib/api/auth', () => ({
	login: vi.fn()
}));

// isGuest is now simply "tokenless" (derived from isAuthenticated) — the test
// helper drives that directly rather than through a role string.
vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _isAuthenticated = writable<boolean>(true);
	return {
		applyLogin: vi.fn(),
		isGuest: derived(_isAuthenticated, (a) => !a),
		// Test-only helper — not part of the real module's public API.
		__setAuthenticated: (a: boolean) => _isAuthenticated.set(a)
	};
});

// The page probes /api/system/version anonymously (raw fetch) to learn
// whether guest access is enabled — stub global fetch per test.
const fetchMock = vi.fn();
beforeEach(() => {
	vi.stubGlobal('fetch', fetchMock);
	fetchMock.mockResolvedValue({ ok: true });
});

describe('Login page Continue as Guest', () => {
	afterEach(async () => {
		cleanup();
		gotoMock.mockClear();
		fetchMock.mockReset();
		vi.unstubAllGlobals();
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(true);
	});

	it('shows the yellow Continue as Guest button when tokenless and guest access is enabled', async () => {
		fetchMock.mockResolvedValue({ ok: true });
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(false);
		renderComponent(LoginPage);

		const btn = await waitFor(() => screen.getByText('Continue as Guest'));
		expect(btn).toBeInTheDocument();
		expect(btn.className).toContain('bg-amber-500');

		await fireEvent.click(btn);
		expect(gotoMock).toHaveBeenCalledWith('/');
	});

	it('hides the button when guest access is disabled (probe 401)', async () => {
		fetchMock.mockResolvedValue({ ok: false, status: 401 });
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(false);
		renderComponent(LoginPage);

		await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/system/version'));
		expect(screen.queryByText('Continue as Guest')).not.toBeInTheDocument();
	});

	it('hides the button when authenticated', async () => {
		fetchMock.mockResolvedValue({ ok: true });
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(true);
		renderComponent(LoginPage);

		await waitFor(() => expect(fetchMock).toHaveBeenCalled());
		expect(screen.queryByText('Continue as Guest')).not.toBeInTheDocument();
	});

	it('hides the button when the probe itself fails (backend down)', async () => {
		fetchMock.mockRejectedValue(new Error('network'));
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(false);
		renderComponent(LoginPage);

		await waitFor(() => expect(fetchMock).toHaveBeenCalled());
		expect(screen.queryByText('Continue as Guest')).not.toBeInTheDocument();
	});
});
