import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
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

describe('Login page guest escape hatch', () => {
	afterEach(async () => {
		cleanup();
		gotoMock.mockClear();
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(true);
	});

	it('login page offers "Continue browsing as guest" when tokenless', async () => {
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(false);
		renderComponent(LoginPage);

		const escapeHatch = screen.getByText('← Continue browsing as guest');
		expect(escapeHatch).toBeInTheDocument();

		await fireEvent.click(escapeHatch);
		expect(gotoMock).toHaveBeenCalledWith('/');
	});

	it('login page hides the guest escape hatch when authenticated', async () => {
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setAuthenticated: (a: boolean) => void;
		};
		auth.__setAuthenticated(true);
		renderComponent(LoginPage);

		expect(screen.queryByText('← Continue browsing as guest')).not.toBeInTheDocument();
	});
});
