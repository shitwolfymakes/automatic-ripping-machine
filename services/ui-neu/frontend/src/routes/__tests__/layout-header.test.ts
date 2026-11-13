import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import Layout from '../+layout.svelte';
import { createRawSnippet } from 'svelte';
import type { Writable } from 'svelte/store';
import { dashboard } from '$lib/stores/dashboard';
import { theme, toggleTheme } from '$lib/stores/theme';
import { schemeLocksMode } from '$lib/stores/color-scheme';
import { setRippingEnabled } from '$lib/api/config';
import { setUiPref } from '$lib/stores/ui-prefs';
import { showIsoPicker, isoPickerMode } from '$lib/stores/iso-picker';

// Writable page store: the setup page and the nav highlight key off pathname.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	const _page = writable({ url: { pathname: '/' }, params: {} });
	return {
		page: { subscribe: _page.subscribe },
		__setPathname: (pathname: string) => _page.set({ url: { pathname }, params: {} })
	};
});

async function setPathname(pathname: string) {
	const stores = (await import('$app/stores')) as unknown as {
		__setPathname: (p: string) => void;
	};
	stores.__setPathname(pathname);
}

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({
	goto: (...args: unknown[]) => gotoMock(...args)
}));

vi.mock('$lib/api/client', () => ({
	setUnauthorizedHandler: vi.fn(),
	getToken: () => 'admin-token'
}));

vi.mock('$lib/api/auth', () => ({
	logout: vi.fn(() => Promise.resolve())
}));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	const _isAuthenticated = writable<boolean>(true);
	return {
		initAuth: vi.fn(),
		logoutLocal: vi.fn(),
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_isAuthenticated, (a) => !a),
		__setSession: (kind: 'admin' | 'guest') => {
			_role.set(kind === 'admin' ? 'admin' : null);
			_isAuthenticated.set(kind === 'admin');
		}
	};
});

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/color-scheme', async () => {
	const { writable } = await import('svelte/store');
	return {
		colorScheme: writable('default'),
		schemeLocksMode: writable(false),
		loadThemesFromApi: vi.fn()
	};
});

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({});
	return { dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) } };
});

vi.mock('$lib/api/config', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/api/config')>()),
	setRippingEnabled: vi.fn(() => Promise.resolve())
}));

const startIsoRipMock = vi.fn(() => Promise.resolve({ drive_id: 'drive-1' }));
vi.mock('$lib/api/iso', () => ({
	fetchIsoFolders: vi.fn(() => Promise.resolve({ host_path: '/mnt/iso', entries: [], partial: false })),
	fetchIsoLibrary: vi.fn(() =>
		Promise.resolve({
			host_path: '/mnt/iso',
			subpath: '',
			parent_subpath: null,
			entries: [
				{ name: 'movie.iso', kind: 'iso', size_bytes: 1024, modified_at: '2025-01-01T00:00:00Z', ripping: false }
			]
		})
	),
	startIsoRip: () => startIsoRipMock(),
	cancelIsoRip: vi.fn()
}));
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));

type DashState = Record<string, unknown>;

function baseState(): DashState {
	return {
		db_available: true,
		arm_online: true,
		active_jobs: [],
		drives_online: 2,
		drive_names: {},
		notification_count: 0,
		ripping_enabled: true,
		makemkv_key_valid: true,
		makemkv_key_checked_at: null,
		transcoder_online: false,
		transcoder_stats: null,
		active_transcodes: []
	};
}

function setDash(patch: DashState) {
	dashboard.update(() => ({ ...baseState(), ...patch }) as never);
}

function setSchemeLocksMode(locked: boolean) {
	(schemeLocksMode as unknown as Writable<boolean>).set(locked);
}

function childSnippet() {
	return createRawSnippet(() => ({ render: () => '<p>Page Content</p>' }));
}

function renderLayout() {
	return renderComponent(Layout, { props: { children: childSnippet() } });
}

async function setSession(kind: 'admin' | 'guest') {
	const auth = (await import('$lib/stores/auth')) as unknown as {
		__setSession: (k: 'admin' | 'guest') => void;
	};
	auth.__setSession(kind);
}

function healthLink(label: string): HTMLElement {
	const link = Array.from(document.querySelectorAll<HTMLElement>('.layout-health-link')).find(
		(el) => el.textContent?.trim() === label
	);
	if (!link) throw new Error(`no health link ${label}`);
	return link;
}

function dotStatus(label: string): string | null {
	return healthLink(label).querySelector('.status-dot')!.getAttribute('data-status');
}

function activityLink(): HTMLElement {
	return document.querySelector<HTMLElement>('.layout-activity-link')!;
}

beforeEach(() => {
	setDash({});
});

afterEach(async () => {
	cleanup();
	gotoMock.mockClear();
	vi.mocked(setRippingEnabled).mockReset();
	vi.mocked(setRippingEnabled).mockResolvedValue(undefined as never);
	vi.mocked(toggleTheme).mockClear();
	startIsoRipMock.mockClear();
	theme.set('dark');
	setSchemeLocksMode(false);
	showIsoPicker.set(false);
	isoPickerMode.set('iso');
	setUiPref('showStats', true);
	await setSession('admin');
	await setPathname('/');
});

describe('Layout header service dots', () => {
	it('shows ARM ok when online and error when offline', () => {
		renderLayout();
		expect(dotStatus('ARM')).toBe('ok');
		cleanup();
		setDash({ arm_online: false });
		renderLayout();
		expect(dotStatus('ARM')).toBe('error');
	});

	it('shows DB ok when available and warn when not', () => {
		renderLayout();
		expect(dotStatus('DB')).toBe('ok');
		cleanup();
		setDash({ db_available: false });
		renderLayout();
		expect(dotStatus('DB')).toBe('warn');
	});

	it('shows the transcoder ok when online with no stats yet', () => {
		setDash({ transcoder_online: true, transcoder_stats: null });
		renderLayout();
		expect(dotStatus('Transcode')).toBe('ok');
	});

	it('shows the transcoder ok when online with a running worker', () => {
		setDash({ transcoder_online: true, transcoder_stats: { worker_running: true } });
		renderLayout();
		expect(dotStatus('Transcode')).toBe('ok');
	});

	it('shows the transcoder warn when online but the worker is not running', () => {
		setDash({ transcoder_online: true, transcoder_stats: { worker_running: false } });
		renderLayout();
		expect(dotStatus('Transcode')).toBe('warn');
	});

	it('shows the transcoder off when offline', () => {
		setDash({ transcoder_online: false });
		renderLayout();
		expect(dotStatus('Transcode')).toBe('off');
	});
});

describe('Layout header MakeMKV key', () => {
	it('titles a valid key with its check time and shows an ok dot', () => {
		const checked = '2025-03-04T05:06:07Z';
		setDash({ makemkv_key_valid: true, makemkv_key_checked_at: checked });
		renderLayout();
		expect(healthLink('Key').getAttribute('title')).toBe(
			`MakeMKV key valid - checked ${new Date(checked).toLocaleString()}`
		);
		expect(dotStatus('Key')).toBe('ok');
	});

	it('titles a valid key without a check time', () => {
		setDash({ makemkv_key_valid: true, makemkv_key_checked_at: null });
		renderLayout();
		expect(healthLink('Key').getAttribute('title')).toBe('MakeMKV key valid');
	});

	it('titles an invalid key and shows an error dot', () => {
		setDash({ makemkv_key_valid: false });
		renderLayout();
		expect(healthLink('Key').getAttribute('title')).toBe('MakeMKV key invalid - click to update');
		expect(dotStatus('Key')).toBe('error');
	});

	it('titles an unchecked key and shows an error dot', () => {
		setDash({ makemkv_key_valid: null });
		renderLayout();
		expect(healthLink('Key').getAttribute('title')).toBe('MakeMKV key not checked yet');
		expect(dotStatus('Key')).toBe('error');
	});
});

describe('Layout header activity counts', () => {
	it('shows -- for the drive count when the DB is unavailable', () => {
		setDash({ db_available: false, drives_online: 3 });
		renderLayout();
		expect(activityLink().textContent).toBe('-- drives');
	});

	it('shows an empty count when the DB is up but reports no drive count', () => {
		setDash({ drives_online: undefined });
		renderLayout();
		expect(activityLink().textContent).toBe(' drives');
	});

	it('uses the singular for one drive and the plural otherwise', () => {
		setDash({ drives_online: 1 });
		renderLayout();
		expect(activityLink().textContent).toBe('1 drive');
		cleanup();
		setDash({ drives_online: 2 });
		renderLayout();
		expect(activityLink().textContent).toBe('2 drives');
	});

	it('hides the ripping, transcoding, queued and notification counts when zero', () => {
		renderLayout();
		expect(document.querySelector('.layout-activity-ripping')).toBeNull();
		expect(document.querySelector('.layout-activity-transcoding')).toBeNull();
		expect(document.querySelector('.layout-activity-queued')).toBeNull();
		expect(document.querySelector('.layout-activity-notification')).toBeNull();
	});

	it('copes with a dashboard that has no job list or notification count', () => {
		setDash({ active_jobs: undefined, notification_count: undefined });
		renderLayout();
		expect(document.querySelector('.layout-activity-ripping')).toBeNull();
		expect(document.querySelector('.layout-activity-notification')).toBeNull();
		expect(document.querySelector('.nav-badge')).toBeNull();
	});

	it('shows the ripping count', () => {
		setDash({ active_jobs: [{ job_id: 1, status: 'ripping', title: 'A' }] });
		renderLayout();
		expect(document.querySelector('.layout-activity-ripping')!.textContent).toBe('1 ripping');
	});

	it('shows the transcoding count as a link to /transcoder', () => {
		setDash({ active_transcodes: [{}, {}] });
		renderLayout();
		const el = document.querySelector('.layout-activity-transcoding')!;
		expect(el.textContent).toBe('2 transcoding');
		expect(el.getAttribute('href')).toBe('/transcoder');
	});

	it('shows the queued count only while the transcoder is online', () => {
		setDash({ transcoder_online: true, transcoder_stats: { pending: 4 } });
		renderLayout();
		expect(document.querySelector('.layout-activity-queued')!.textContent).toBe('4 queued');
		cleanup();
		setDash({ transcoder_online: true, transcoder_stats: { pending: 'none' } });
		renderLayout();
		expect(document.querySelector('.layout-activity-queued')).toBeNull();
		cleanup();
		setDash({ transcoder_online: true, transcoder_stats: null });
		renderLayout();
		expect(document.querySelector('.layout-activity-queued')).toBeNull();
		cleanup();
		setDash({ transcoder_online: false, transcoder_stats: { pending: 4 } });
		renderLayout();
		expect(document.querySelector('.layout-activity-queued')).toBeNull();
	});

	it('shows one notification in the singular, linked to /notifications', () => {
		setDash({ notification_count: 1 });
		renderLayout();
		const el = document.querySelector('.layout-activity-notification')!;
		expect(el.textContent).toBe('1 notification');
		expect(el.getAttribute('href')).toBe('/notifications');
	});

	it('shows several notifications in the plural and badges the nav item', () => {
		setDash({ notification_count: 3 });
		renderLayout();
		expect(document.querySelector('.layout-activity-notification')!.textContent).toBe('3 notifications');
		expect(document.querySelector('aside .nav-badge')!.textContent).toBe('3');
	});
});

describe('Layout Auto-Start toggle', () => {
	it('is hidden for guests and when the DB is unavailable', async () => {
		await setSession('guest');
		renderLayout();
		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
		cleanup();
		await setSession('admin');
		setDash({ db_available: false });
		renderLayout();
		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
	});

	it('pauses ripping and labels the switch Paused', async () => {
		renderLayout();
		const toggle = screen.getByRole('switch');
		expect(toggle).toHaveAttribute('aria-checked', 'true');
		expect(toggle).toHaveTextContent('Auto-Start');
		await fireEvent.click(toggle);
		expect(setRippingEnabled).toHaveBeenCalledWith(false);
		await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'));
		expect(toggle).toHaveTextContent('Paused');
		expect(toggle).not.toBeDisabled();
	});

	it('reverts the switch when the server rejects the change', async () => {
		vi.mocked(setRippingEnabled).mockRejectedValueOnce(new Error('boom'));
		renderLayout();
		const toggle = screen.getByRole('switch');
		await fireEvent.click(toggle);
		await waitFor(() => expect(setRippingEnabled).toHaveBeenCalledTimes(1));
		await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
		expect(toggle).toHaveTextContent('Auto-Start');
		expect(toggle).not.toBeDisabled();
	});

	it('ignores a click while a toggle is still in flight', async () => {
		let release!: () => void;
		vi.mocked(setRippingEnabled).mockReturnValueOnce(
			new Promise<undefined>((resolve) => {
				release = () => resolve(undefined);
			}) as never
		);
		renderLayout();
		const toggle = screen.getByRole('switch');
		await fireEvent.click(toggle);
		await waitFor(() => expect(toggle).toBeDisabled());
		// Re-enable by hand so the click reaches the handler's in-flight guard.
		toggle.removeAttribute('disabled');
		await fireEvent.click(toggle);
		expect(setRippingEnabled).toHaveBeenCalledTimes(1);
		release();
		await waitFor(() => expect(toggle).not.toBeDisabled());
	});
});

describe('Layout quick actions', () => {
	it('Rip from ISO opens the picker in ISO mode and closes the flyout', async () => {
		renderLayout();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from ISO' }));
		expect(await screen.findByRole('heading', { name: 'Rip from ISO' })).toBeInTheDocument();
		expect(screen.queryByRole('menuitem', { name: 'Rip from ISO' })).not.toBeInTheDocument();
	});

	it('Rip from folder opens the picker in folder mode', async () => {
		renderLayout();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from folder' }));
		expect(await screen.findByRole('heading', { name: 'Rip from folder' })).toBeInTheDocument();
	});

	it('Settings navigates to /settings', async () => {
		renderLayout();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
		expect(gotoMock).toHaveBeenCalledWith('/settings');
	});

	it('Cancel in the picker closes it', async () => {
		renderLayout();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from ISO' }));
		await screen.findByRole('heading', { name: 'Rip from ISO' });
		await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('heading', { name: 'Rip from ISO' })).not.toBeInTheDocument());
	});

	it('starting a rip closes the picker', async () => {
		renderLayout();
		await fireEvent.click(screen.getByTitle('Quick actions'));
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Rip from ISO' }));
		await fireEvent.click(await screen.findByRole('option', { name: 'movie.iso' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));
		await waitFor(() => expect(startIsoRipMock).toHaveBeenCalledTimes(1));
		await waitFor(() => expect(screen.queryByRole('heading', { name: 'Rip from ISO' })).not.toBeInTheDocument());
	});
});

describe('Layout header buttons', () => {
	it('Login sends a guest to /login', async () => {
		await setSession('guest');
		renderLayout();
		await fireEvent.click(screen.getByText('Login'));
		expect(gotoMock).toHaveBeenCalledWith('/login');
	});

	it('shows the sun icon on the dark theme and the moon icon on the light theme', () => {
		renderLayout();
		const sun = screen.getByTitle('Switch theme').querySelector('path')!.getAttribute('d');
		expect(sun).toContain('M12 3v1');
		cleanup();
		theme.set('light');
		renderLayout();
		const moon = screen.getByTitle('Switch theme').querySelector('path')!.getAttribute('d');
		expect(moon).toContain('M20.354 15.354');
	});

	it('the theme button calls toggleTheme', async () => {
		renderLayout();
		await fireEvent.click(screen.getByLabelText('Switch theme'));
		expect(toggleTheme).toHaveBeenCalledTimes(1);
	});

	it('hides the theme button when the colour scheme locks the mode', () => {
		setSchemeLocksMode(true);
		renderLayout();
		expect(screen.queryByLabelText('Switch theme')).not.toBeInTheDocument();
	});
});

describe('Layout mobile drawer', () => {
	it('the sidebar toggle opens the drawer and a second press closes it', async () => {
		renderLayout();
		expect(screen.queryByLabelText('Close sidebar')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		expect(screen.getByLabelText('Close sidebar')).toBeInTheDocument();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		expect(screen.queryByLabelText('Close sidebar')).not.toBeInTheDocument();
	});

	it('badges the Notifications item in the drawer menu', async () => {
		setDash({ notification_count: 5 });
		renderLayout();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		const drawer = document.querySelector('.layout-drawer')!;
		expect(drawer.querySelector('.nav-badge')!.textContent).toBe('5');
	});

	it('leaves the drawer menu unbadged when there is no notification count', async () => {
		setDash({ notification_count: undefined });
		renderLayout();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		const drawer = document.querySelector('.layout-drawer')!;
		expect(drawer.querySelector('a[href="/notifications"]')).not.toBeNull();
		expect(drawer.querySelector('.nav-badge')).toBeNull();
	});

	it('closes when a menu link is clicked', async () => {
		renderLayout();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		const link = document.querySelector('.layout-drawer a[href="/logs"]')!;
		await fireEvent.click(link);
		expect(screen.queryByLabelText('Close sidebar')).not.toBeInTheDocument();
	});

	it('switches between Menu and Stats and closes from a link in the Stats view', async () => {
		renderLayout();
		await fireEvent.click(screen.getByLabelText('Toggle sidebar'));
		await fireEvent.click(screen.getByRole('button', { name: 'Stats' }));
		expect(document.querySelector('[data-mobile-stats]')).not.toBeNull();
		await fireEvent.click(document.querySelector('[data-mobile-stats] a[href="/transcoder"]')!);
		expect(screen.queryByLabelText('Close sidebar')).not.toBeInTheDocument();
	});
});

describe('Layout setup page', () => {
	it('renders the page bare, with no header, sidebar or bottom bar', async () => {
		setUiPref('showStats', true);
		await setPathname('/setup');
		renderLayout();
		expect(screen.getByText('Page Content')).toBeInTheDocument();
		expect(screen.queryByLabelText('Toggle sidebar')).not.toBeInTheDocument();
		expect(document.querySelector('[data-sidebar]')).toBeNull();
		expect(document.querySelector('[data-testid="bottom-stats-bar"]')).toBeNull();
	});
});
