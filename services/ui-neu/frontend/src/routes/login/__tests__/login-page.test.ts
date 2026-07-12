import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import LoginPage from '../+page.svelte';

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({
	goto: (...args: unknown[]) => gotoMock(...args)
}));

vi.mock('$lib/api/auth', () => ({
	login: vi.fn(),
	guestLogin: vi.fn()
}));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		applyLogin: vi.fn(),
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_role, (r) => r === 'guest'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

describe('Login page guest escape hatch', () => {
	afterEach(async () => {
		cleanup();
		gotoMock.mockClear();
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setRole: (r: string | null) => void;
		};
		auth.__setRole('admin');
	});

	it('login page offers "Continue browsing as guest" for guest sessions', async () => {
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setRole: (r: string | null) => void;
		};
		auth.__setRole('guest');
		renderComponent(LoginPage);

		const escapeHatch = screen.getByText('← Continue browsing as guest');
		expect(escapeHatch).toBeInTheDocument();

		await fireEvent.click(escapeHatch);
		expect(gotoMock).toHaveBeenCalledWith('/');
	});

	it('login page hides the guest escape hatch when no guest session', async () => {
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setRole: (r: string | null) => void;
		};
		auth.__setRole('admin');
		renderComponent(LoginPage);

		expect(screen.queryByText('← Continue browsing as guest')).not.toBeInTheDocument();
	});
});
