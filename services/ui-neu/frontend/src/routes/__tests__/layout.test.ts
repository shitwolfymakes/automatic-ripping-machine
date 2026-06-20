import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import Layout from '../+layout.svelte';
import { createRawSnippet } from 'svelte';

vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ url: { pathname: '/' }, params: {} }) };
});

// Capture the unauthorized handler the layout registers, so the test can fire
// a simulated session-expiry 401 and assert the layout's response.
let capturedOn401: (() => void) | null = null;
vi.mock('$lib/api/client', () => ({
	setUnauthorizedHandler: (fn: () => void) => {
		capturedOn401 = fn;
	}
}));

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...args: unknown[]) => gotoMock(...args) }));

const logoutLocalMock = vi.fn();
vi.mock('$lib/stores/auth', () => ({
	initAuth: vi.fn(),
	logoutLocal: () => logoutLocalMock()
}));

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
		db_available: true, arm_online: true, active_jobs: [],
		drives_online: 0, drive_names: {}, notification_count: 0, ripping_enabled: true,
		transcoder_online: false, transcoder_stats: null,
		active_transcodes: []
	});
	return { dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) } };
});

vi.mock('$lib/api/dashboard', () => ({
	setRippingEnabled: vi.fn(() => Promise.resolve())
}));

function childSnippet() {
	return createRawSnippet(() => ({
		render: () => '<p>Page Content</p>'
	}));
}

describe('Layout', () => {
	afterEach(() => {
		cleanup();
		capturedOn401 = null;
		gotoMock.mockClear();
		logoutLocalMock.mockClear();
	});

	describe('session expiry (401 handler)', () => {
		it('stops dashboard polling when the session goes stale', async () => {
			const { dashboard } = await import('$lib/stores/dashboard');
			renderComponent(Layout, { props: { children: childSnippet() } });
			expect(capturedOn401).toBeTypeOf('function');
			(dashboard.stop as ReturnType<typeof vi.fn>).mockClear();

			// Simulate a poll request 401ing after the session expired.
			capturedOn401!();

			// The poll loop MUST be stopped so it can't keep 401-storming.
			expect(dashboard.stop).toHaveBeenCalled();
			expect(logoutLocalMock).toHaveBeenCalled();
			expect(gotoMock).toHaveBeenCalledWith('/login');
		});

		it('does not re-navigate on repeated 401s once already on /login', async () => {
			renderComponent(Layout, { props: { children: childSnippet() } });
			// First 401 redirects to /login.
			capturedOn401!();
			expect(gotoMock).toHaveBeenCalledTimes(1);
			gotoMock.mockClear();

			// The dashboard's allSettled fan-out fires on401 once per failed
			// request (6 endpoints) per tick. Subsequent fires must NOT pile up
			// redundant goto('/login') calls (which deselect login inputs).
			capturedOn401!();
			capturedOn401!();
			expect(gotoMock).not.toHaveBeenCalled();
		});
	});

	it('renders navigation links for v3-supported screens', () => {
		renderComponent(Layout, { props: { children: childSnippet() } });
		expect(screen.getByText('Dashboard')).toBeInTheDocument();
		expect(screen.getByText('Notifications')).toBeInTheDocument();
		expect(screen.getByText('Settings')).toBeInTheDocument();
	});

	it('hides nav items for feature-flagged-off screens (Files — MISSING in v3)', () => {
		renderComponent(Layout, { props: { children: childSnippet() } });
		expect(screen.queryByText('Files')).not.toBeInTheDocument();
	});

	it('shows the Logs nav item (job-scoped log browser is enabled)', () => {
		renderComponent(Layout, { props: { children: childSnippet() } });
		expect(screen.getByText('Logs')).toBeInTheDocument();
	});

	it('renders children content', () => {
		renderComponent(Layout, { props: { children: childSnippet() } });
		expect(screen.getByText('Page Content')).toBeInTheDocument();
	});

	it('renders ARM logo', () => {
		renderComponent(Layout, { props: { children: childSnippet() } });
		const logos = screen.getAllByAltText('ARM');
		expect(logos.length).toBeGreaterThanOrEqual(1);
	});

	it('topnav ripping count excludes transcoding jobs', async () => {
		const { dashboard } = await import('$lib/stores/dashboard');

		// Set active_jobs with one ripping and one transcoding job
		dashboard.update(() => ({
			db_available: true, arm_online: true,
			active_jobs: [
				{ job_id: 1, status: 'ripping', title: 'Movie A' },
				{ job_id: 2, status: 'transcoding', title: 'Movie B' },
			] as never[],
			drives_online: 1, drive_names: {},
			notification_count: 0, ripping_enabled: true,
			makemkv_key_valid: null, makemkv_key_checked_at: null,
			transcoder_online: false, transcoder_stats: null,
			active_transcodes: []
		}));

		renderComponent(Layout, { props: { children: childSnippet() } });

		// Should show "1 ripping", not "2 ripping"
		const rippingBadges = screen.getAllByText(/ripping/i);
		const rippingBadge = rippingBadges.find(el => el.textContent?.match(/^\d+ ripping$/));
		expect(rippingBadge?.textContent).toBe('1 ripping');
	});
});
