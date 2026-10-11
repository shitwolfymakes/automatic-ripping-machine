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
		expect(btn.className).toContain('btn-warning');

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

describe('Login page on first run (setup spec §5.1)', () => {
	function firstRunFetch(firstRun: boolean) {
		fetchMock.mockImplementation((url: string) =>
			Promise.resolve(
				url === '/api/setup/status'
					? { ok: true, json: () => Promise.resolve({ first_run: firstRun, arm_version: '3.1.0' }) }
					: { ok: true }
			)
		);
	}

	afterEach(async () => {
		cleanup();
		gotoMock.mockClear();
		fetchMock.mockReset();
		vi.unstubAllGlobals();
		const auth = (await import('$lib/stores/auth')) as unknown as { __setAuthenticated: (a: boolean) => void };
		auth.__setAuthenticated(true);
	});

	it('says where the first-boot password is and hides Continue as Guest', async () => {
		firstRunFetch(true);
		const auth = (await import('$lib/stores/auth')) as unknown as { __setAuthenticated: (a: boolean) => void };
		auth.__setAuthenticated(false);
		renderComponent(LoginPage);
		expect(await screen.findByTestId('login-first-run')).toHaveTextContent(/first time\?/i);
		expect(screen.getByText('docker exec armv3-backend cat /logs/first-boot.log')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /continue as guest/i })).toBeNull();
	});

	it('sends the admin into setup after signing in', async () => {
		firstRunFetch(true);
		const { login } = await import('$lib/api/auth');
		vi.mocked(login).mockResolvedValue({
			access_token: 't',
			expires_at: '',
			password_must_change: true,
			role: 'admin'
		});
		renderComponent(LoginPage);
		await screen.findByTestId('login-first-run');
		await fireEvent.input(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
		await fireEvent.input(screen.getByLabelText(/password/i), { target: { value: 'admin' } });
		await fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/setup'));
	});

	it('keeps the forced password change when setup is already done', async () => {
		firstRunFetch(false);
		const { login } = await import('$lib/api/auth');
		vi.mocked(login).mockResolvedValue({
			access_token: 't',
			expires_at: '',
			password_must_change: true,
			role: 'admin'
		});
		renderComponent(LoginPage);
		await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/setup/status'));
		await fireEvent.input(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
		await fireEvent.input(screen.getByLabelText(/password/i), { target: { value: 'x' } });
		await fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/change-password'));
		expect(screen.queryByTestId('login-first-run')).toBeNull();
	});
});
