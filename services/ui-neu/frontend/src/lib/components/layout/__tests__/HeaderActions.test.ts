import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import { get, writable } from 'svelte/store';

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({
	goto: (...args: unknown[]) => gotoMock(...args)
}));

const apiLogoutMock = vi.fn();
vi.mock('$lib/api/auth', () => ({
	logout: () => apiLogoutMock()
}));

const logoutLocalMock = vi.fn();
vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	const _authed = writable<boolean>(true);
	return {
		logoutLocal: () => logoutLocalMock(),
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_authed, (a) => !a),
		__setSession: (kind: 'admin' | 'user' | 'guest') => {
			_role.set(kind === 'admin' ? 'admin' : null);
			_authed.set(kind !== 'guest');
		}
	};
});

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/color-scheme', async () => {
	const { writable } = await import('svelte/store');
	return { schemeLocksMode: writable(false) };
});

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	return { dashboard: writable({}) };
});

vi.mock('$lib/api/config', () => ({
	setRippingEnabled: vi.fn(() => Promise.resolve())
}));

import HeaderActions from '../HeaderActions.svelte';
import * as authModule from '$lib/stores/auth';
import { dashboard } from '$lib/stores/dashboard';
import { theme, toggleTheme } from '$lib/stores/theme';
import { schemeLocksMode } from '$lib/stores/color-scheme';
import { setRippingEnabled } from '$lib/api/config';
import { showIsoPicker, isoPickerMode } from '$lib/stores/iso-picker';

const setSession = (authModule as unknown as { __setSession: (k: 'admin' | 'user' | 'guest') => void }).__setSession;

function setDash(patch: Record<string, unknown> = {}) {
	(dashboard as unknown as { set: (v: unknown) => void }).set({
		db_available: true,
		ripping_enabled: true,
		...patch
	});
}

const render = () => renderComponent(HeaderActions, { props: {} });
const dashState = () => get(dashboard as unknown as ReturnType<typeof writable<Record<string, unknown>>>);
const autoStart = () => screen.getByRole('switch');

beforeEach(() => {
	setSession('admin');
	setDash();
	apiLogoutMock.mockResolvedValue(undefined);
	vi.mocked(setRippingEnabled).mockResolvedValue(undefined as never);
});

afterEach(() => {
	cleanup();
	gotoMock.mockClear();
	apiLogoutMock.mockReset();
	logoutLocalMock.mockClear();
	vi.mocked(setRippingEnabled).mockReset();
	vi.mocked(toggleTheme).mockClear();
	theme.set('dark');
	(schemeLocksMode as unknown as { set: (v: boolean) => void }).set(false);
	showIsoPicker.set(false);
	isoPickerMode.set('iso');
});

describe('HeaderActions auto-start toggle', () => {
	it('reads Auto-Start and is checked while ripping is enabled', () => {
		render();
		expect(autoStart()).toHaveTextContent('Auto-Start');
		expect(autoStart()).toHaveAttribute('aria-checked', 'true');
	});

	it('reads Paused when ripping is disabled', () => {
		setDash({ ripping_enabled: false });
		render();
		expect(autoStart()).toHaveTextContent('Paused');
		expect(autoStart()).toHaveAttribute('aria-checked', 'false');
	});

	it('is hidden when the database is unavailable', () => {
		setDash({ db_available: false });
		render();
		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
	});

	it('is hidden from guests', () => {
		setSession('guest');
		render();
		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
	});

	it('flips optimistically, calls the API and stays flipped on success', async () => {
		render();
		await fireEvent.click(autoStart());
		expect(setRippingEnabled).toHaveBeenCalledWith(false);
		await waitFor(() => expect(autoStart()).not.toBeDisabled());
		expect(dashState().ripping_enabled).toBe(false);
	});

	it('reverts the flip when the API call fails', async () => {
		vi.mocked(setRippingEnabled).mockRejectedValueOnce(new Error('boom'));
		render();
		await fireEvent.click(autoStart());
		await waitFor(() => expect(dashState().ripping_enabled).toBe(true));
		expect(autoStart()).not.toBeDisabled();
	});

	it('ignores a second click while the first is in flight', async () => {
		let resolve!: () => void;
		vi.mocked(setRippingEnabled).mockReturnValueOnce(new Promise<void>((r) => (resolve = r)) as never);
		render();
		const button = autoStart();
		await fireEvent.click(button);
		expect(button).toBeDisabled();
		// Fire the handler directly: a disabled button swallows real clicks.
		button.removeAttribute('disabled');
		await fireEvent.click(button);
		expect(setRippingEnabled).toHaveBeenCalledTimes(1);
		resolve();
		await waitFor(() => expect(button).not.toBeDisabled());
	});
});

describe('HeaderActions quick actions menu', () => {
	it('is hidden from guests', () => {
		setSession('guest');
		render();
		expect(screen.queryByTitle('Quick actions')).not.toBeInTheDocument();
	});

	it('offers the rip entries and Settings to an admin', async () => {
		render();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		expect(screen.getByRole('menuitem', { name: 'Rip from ISO' })).toBeInTheDocument();
		expect(screen.getByRole('menuitem', { name: 'Rip from folder' })).toBeInTheDocument();
		expect(screen.getByRole('menuitem', { name: 'Settings' })).toBeInTheDocument();
	});

	it('offers only Settings to a signed-in non-admin', async () => {
		setSession('user');
		render();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		expect(screen.queryByRole('menuitem', { name: 'Rip from ISO' })).not.toBeInTheDocument();
		expect(screen.queryByRole('menuitem', { name: 'Rip from folder' })).not.toBeInTheDocument();
		expect(screen.getByRole('menuitem', { name: 'Settings' })).toBeInTheDocument();
	});

	it('Rip from ISO opens the picker in ISO mode and closes the flyout', async () => {
		isoPickerMode.set('folder');
		render();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from ISO' }));
		expect(get(isoPickerMode)).toBe('iso');
		expect(get(showIsoPicker)).toBe(true);
		expect(screen.queryByRole('menuitem', { name: 'Rip from ISO' })).not.toBeInTheDocument();
	});

	it('Rip from folder opens the picker in folder mode and closes the flyout', async () => {
		render();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from folder' }));
		expect(get(isoPickerMode)).toBe('folder');
		expect(get(showIsoPicker)).toBe(true);
		expect(screen.queryByRole('menuitem', { name: 'Rip from folder' })).not.toBeInTheDocument();
	});

	it('Settings navigates to /settings and closes the flyout', async () => {
		render();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
		expect(gotoMock).toHaveBeenCalledWith('/settings');
		expect(screen.queryByRole('menuitem', { name: 'Settings' })).not.toBeInTheDocument();
	});
});

describe('HeaderActions login and sign out', () => {
	it('shows Login to a guest, who goes to /login', async () => {
		setSession('guest');
		render();
		expect(screen.queryByTitle('Sign out')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByTitle('Log in'));
		expect(gotoMock).toHaveBeenCalledWith('/login');
	});

	it('shows Sign out to a signed-in user instead of Login', () => {
		render();
		expect(screen.queryByTitle('Log in')).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
	});

	it('Sign out logs out on the server, drops the local session and goes home', async () => {
		render();
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/'));
		expect(apiLogoutMock).toHaveBeenCalledTimes(1);
		expect(logoutLocalMock).toHaveBeenCalledTimes(1);
	});

	it('Sign out still clears the local session when the server logout fails', async () => {
		apiLogoutMock.mockRejectedValueOnce(new Error('network'));
		render();
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/'));
		expect(logoutLocalMock).toHaveBeenCalledTimes(1);
	});
});

describe('HeaderActions theme toggle', () => {
	it('calls toggleTheme on click', async () => {
		render();
		await fireEvent.click(screen.getByRole('button', { name: 'Switch theme' }));
		expect(toggleTheme).toHaveBeenCalledTimes(1);
	});

	it('draws the sun icon in dark mode and the moon icon in light mode', () => {
		const { container } = render();
		const darkPath = container.querySelector('[aria-label="Switch theme"] path')!.getAttribute('d');
		cleanup();
		theme.set('light');
		const { container: light } = render();
		const lightPath = light.querySelector('[aria-label="Switch theme"] path')!.getAttribute('d');
		expect(darkPath).toMatch(/^M12 3v1/);
		expect(lightPath).toMatch(/^M20\.354/);
	});

	it('is hidden when the colour scheme locks the mode', () => {
		(schemeLocksMode as unknown as { set: (v: boolean) => void }).set(true);
		render();
		expect(screen.queryByRole('button', { name: 'Switch theme' })).not.toBeInTheDocument();
	});
});
