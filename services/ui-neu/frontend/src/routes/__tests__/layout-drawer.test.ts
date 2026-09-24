import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import Layout from '../+layout.svelte';
import { createRawSnippet } from 'svelte';

vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ url: { pathname: '/' }, params: {} }) };
});

vi.mock('$lib/api/client', () => ({
	setUnauthorizedHandler: vi.fn(),
	getToken: () => 'admin-token'
}));

vi.mock('$lib/api/auth', () => ({
	logout: vi.fn(() => Promise.resolve())
}));

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		initAuth: vi.fn(),
		logoutLocal: vi.fn(),
		applyLogin: vi.fn(),
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_role, (r) => r === 'guest')
	};
});

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/colorScheme', async () => {
	const { writable } = await import('svelte/store');
	return {
		colorScheme: writable('default'),
		schemeLocksMode: writable(false),
		loadThemesFromApi: vi.fn()
	};
});

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({
		db_available: true,
		arm_online: true,
		active_jobs: [],
		drives_online: 1,
		drive_names: {},
		notification_count: 0,
		ripping_enabled: true,
		makemkv_key_valid: true,
		makemkv_key_checked_at: null,
		transcoder_online: false,
		transcoder_stats: null,
		active_transcodes: []
	});
	return {
		dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) }
	};
});

vi.mock('$lib/api/dashboard', () => ({
	setRippingEnabled: vi.fn(() => Promise.resolve())
}));

function childSnippet() {
	return createRawSnippet(() => ({
		render: () => '<p>Page Content</p>'
	}));
}

function openDrawer() {
	renderComponent(Layout, { props: { children: childSnippet() } });
	const hamburger = screen.getByLabelText('Toggle sidebar');
	return fireEvent.click(hamburger);
}

afterEach(() => cleanup());

describe('Layout mobile drawer Menu/Stats toggle', () => {
	it('opens on the Menu view with a Menu/Stats toggle at the top', async () => {
		await openDrawer();
		expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Stats' })).toBeInTheDocument();
		// Menu view: nav items visible, stats panel absent
		expect(document.querySelector('[data-mobile-stats]')).toBeNull();
	});

	it('switches to the Stats view when Stats is tapped', async () => {
		await openDrawer();
		await fireEvent.click(screen.getByRole('button', { name: 'Stats' }));
		expect(document.querySelector('[data-mobile-stats]')).not.toBeNull();
		expect(screen.getByText('Services')).toBeInTheDocument();
	});

	it('resets to the Menu view when the drawer is reopened', async () => {
		await openDrawer();
		await fireEvent.click(screen.getByRole('button', { name: 'Stats' }));
		expect(document.querySelector('[data-mobile-stats]')).not.toBeNull();

		// Close via the overlay backdrop, then reopen with the hamburger.
		await fireEvent.click(screen.getByLabelText('Close sidebar'));
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));

		expect(document.querySelector('[data-mobile-stats]')).toBeNull();
		expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument();
	});
});
