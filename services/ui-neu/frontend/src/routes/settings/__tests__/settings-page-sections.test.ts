import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/test-utils';
import SettingsPage from '../+page.svelte';
import { goto } from '$app/navigation';
import { fetchSettings, saveArmConfig } from '$lib/api/settings';
import { fetchDrives, fetchDriveDiagnostic, rescanDrives, updateDrive, enrollDrive } from '$lib/api/drives';
import { fetchSessions } from '$lib/api/sessions';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';
import { fetchSessionRoutes } from '$lib/api/sessionRoutes';
import { fetchUsers } from '$lib/api/users';
import { deleteTheme } from '$lib/api/themes';
import { restartSetup } from '$lib/api/setup';
import { fetchImageCacheStats, clearImageCache } from '$lib/api/maintenance';
import { setTranscoderEnabled, setTranscodeRuntimeEnabled } from '$lib/stores/config';
import { theme } from '$lib/stores/theme';
import { colorScheme, allSchemes, schemeLocksMode, loadThemesFromApi } from '$lib/stores/colorScheme';
import type { DriveView } from '$lib/types/api.gen';

// --- Fixtures (copied from settings-page.test.ts) ---

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-ripper-abc',
		device_path: '/dev/sr0',
		display_name: null,
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: null,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		lifecycle: 'enrolled',
		present: true,
		identity_kind: 'by_id',
		serial: 'AAAABBBB000E',
		by_id_name: 'usb-X_AAAABBBB000E-0:0',
		vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX',
		last_error: null,
		current_job: null,
		...over
	} as DriveView;
}

function field(key: string, group: string, over: Record<string, unknown> = {}) {
	return {
		key,
		group,
		tier: 'operator',
		label: key,
		help: '',
		type: 'string',
		editable: true,
		enum_values: null,
		...over
	};
}

const mockSchema = {
	groups: [
		{
			name: 'Identification',
			fields: [
				field('search_provider_movie', 'Identification', {
					label: 'Search movies with',
					type: 'enum',
					enum_values: ['tmdb', 'omdb']
				})
			]
		},
		{
			name: 'Keys',
			fields: [field('tmdb_api_key', 'Keys', { tier: 'secret', label: 'TMDb API key' })]
		},
		{
			name: 'Ripping',
			fields: [field('auto_rip_on_insert', 'Ripping', { label: 'Auto-rip on insert', type: 'bool' })]
		},
		{
			name: 'Transcoding',
			fields: [
				field('transcode_enabled', 'Transcoding', { label: 'Enable transcoding', type: 'bool' }),
				field('auto_transcode_on_idle', 'Transcoding', { label: 'Auto-transcode on idle', type: 'bool' })
			]
		},
		{
			name: 'Notifications',
			fields: [field('notifications_enabled', 'Notifications', { label: 'Enable notifications', type: 'bool' })]
		},
		{
			name: 'System',
			fields: [field('RAW_ROOT', 'System', { tier: 'infra', label: 'Raw root', editable: false })]
		}
	]
};

const mockConfig = {
	search_provider_movie: 'omdb',
	tmdb_api_key: '<hidden>',
	auto_rip_on_insert: true,
	transcode_enabled: true,
	auto_transcode_on_idle: false,
	notifications_enabled: false
};

// The next fetchSettings call resolves with the defaults overlaid with `over`.
function settingsOnce(over: Record<string, unknown> = {}) {
	vi.mocked(fetchSettings).mockResolvedValueOnce({
		config: mockConfig,
		schema: mockSchema,
		infra: { RAW_ROOT: '/raw' },
		arm_config: {},
		transcoder_config: null,
		...over
	} as never);
}

function schemaOf(...names: string[]) {
	return { groups: mockSchema.groups.filter((g) => names.includes(g.name)) };
}

// --- Mocks (modelled on settings-page.test.ts) ---

vi.mock('$app/navigation', async (importOriginal) => ({
	...(await importOriginal<Record<string, unknown>>()),
	goto: vi.fn()
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() =>
		Promise.resolve({
			config: mockConfig,
			schema: mockSchema,
			infra: { RAW_ROOT: '/raw' },
			arm_config: {},
			transcoder_config: null
		})
	),
	saveArmConfig: vi.fn(() => Promise.resolve({ success: true }))
}));

vi.mock('$lib/api/drives', () => ({
	fetchDrives: vi.fn(() => Promise.resolve([])),
	updateDrive: vi.fn(() => Promise.resolve()),
	unenrollDrive: vi.fn(() => Promise.resolve()),
	enrollDrive: vi.fn(() => Promise.resolve()),
	ignoreDrive: vi.fn(() => Promise.resolve()),
	unignoreDrive: vi.fn(() => Promise.resolve()),
	fetchDriveDiagnostic: vi.fn(() => Promise.resolve({ drives: [], system: [] })),
	rescanDrives: vi.fn(() =>
		Promise.resolve({ online: 0, stale: 0, detected: 0, enrolled: 0, ignored: 0, absent: 0, pruned: 0 })
	)
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([])),
	fetchSession: vi.fn(),
	createSession: vi.fn(),
	updateSession: vi.fn(),
	deleteSession: vi.fn(),
	cloneSession: vi.fn(),
	previewTemplate: vi.fn()
}));

vi.mock('$lib/api/sessionRoutes', () => ({
	fetchSessionRoutes: vi.fn(() => Promise.resolve([])),
	upsertSessionRoute: vi.fn(),
	deleteSessionRoute: vi.fn()
}));

vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(() => Promise.resolve([])),
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn(),
	deleteRipPreset: vi.fn()
}));

vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(() => Promise.resolve([])),
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn(),
	deleteTranscodePreset: vi.fn()
}));

vi.mock('$lib/api/themes', () => ({
	uploadTheme: vi.fn(() => Promise.resolve()),
	deleteTheme: vi.fn(() => Promise.resolve())
}));

vi.mock('$lib/api/gpus', () => ({
	fetchGpus: vi.fn(() => Promise.resolve([])),
	updateGpu: vi.fn(),
	deleteGpu: vi.fn()
}));

vi.mock('$lib/api/setup', () => ({
	restartSetup: vi.fn(() => Promise.resolve({}))
}));

// The System and Users tabs mount these; their own fetches are faked so the
// page's tab bodies render without a network.
vi.mock('$lib/api/system', () => ({
	fetchSystemDiagnostics: vi.fn(() => Promise.reject(new Error('checks unavailable'))),
	fetchSystemVersion: vi.fn()
}));

vi.mock('$lib/api/resources', () => ({
	fetchResources: vi.fn(() => Promise.reject(new Error('resources unavailable')))
}));

vi.mock('$lib/api/diagnostics', () => ({
	fetchDiagnostics: vi.fn(() => Promise.resolve({ services: [] }))
}));

vi.mock('$lib/api/users', () => ({
	fetchUsers: vi.fn(() => Promise.resolve([])),
	setUserDisabled: vi.fn(),
	setUserPassword: vi.fn()
}));

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/colorScheme', async () => {
	const { writable } = await import('svelte/store');
	return {
		colorScheme: writable('default'),
		COLOR_SCHEMES: [],
		schemeLocksMode: writable(false),
		allSchemes: writable([]),
		loadThemesFromApi: vi.fn()
	};
});

vi.mock('$lib/api/maintenance', () => ({
	fetchImageCacheStats: vi.fn(() => Promise.resolve({ count: 5, size_bytes: 5242880, size_mb: '5.0' })),
	clearImageCache: vi.fn(() => Promise.resolve({ success: true, cleared: 5, freed_bytes: 5242880 }))
}));

vi.mock('$lib/api/channels', () => ({
	fetchChannels: vi.fn(() => Promise.resolve([])),
	fetchServices: vi.fn(() => Promise.resolve({ featured: [], services: [] })),
	fetchEventTypes: vi.fn(() => Promise.resolve([])),
	fetchDispatches: vi.fn(() => Promise.resolve([])),
	createChannel: vi.fn(),
	updateChannel: vi.fn(),
	deleteChannel: vi.fn(),
	testSendChannel: vi.fn(),
	composeUrl: vi.fn(),
	testConfig: vi.fn()
}));

type FakePoller = { error: Writable<string | null>; refresh: Mock; start: Mock; stop: Mock };
const pollers = vi.hoisted(() => [] as FakePoller[]);

vi.mock('$lib/stores/polling', async () => {
	const { writable } = await import('svelte/store');
	return {
		// Calls the fetcher on start()/refresh() like the settings-page.test.ts
		// fake, and records each store so a test can drive its error store.
		createPollingStore: vi.fn((fetcher: () => Promise<unknown>, initialValue: unknown) => {
			const data = writable(initialValue);
			async function load() {
				try {
					data.set(await fetcher());
				} catch {
					// the polling error store is driven directly by the tests
				}
			}
			const poller = {
				subscribe: data.subscribe,
				data,
				loading: writable(false),
				error: writable<string | null>(null),
				initialized: writable(true),
				refresh: vi.fn(load),
				start: vi.fn(load),
				stop: vi.fn()
			};
			pollers.push(poller);
			return poller;
		})
	};
});

// --- Helpers ---

const writableOf = <T>(store: unknown) => store as Writable<T>;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

function lastPoller(): FakePoller {
	return pollers[pollers.length - 1];
}

// The Sessions tab body carries its own tablist, so the page's bar comes first.
const tab = (name: string) => screen.getAllByRole('tab', { name })[0];
const tabNames = () => screen.getAllByRole('tab').map((t) => t.textContent?.trim());
const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

async function renderReady() {
	renderComponent(SettingsPage);
	await screen.findByRole('tab', { name: 'Sessions' });
}

async function openTab(name: string) {
	await renderReady();
	await fireEvent.click(tab(name));
}

describe('Settings page sections', () => {
	let main: HTMLElement;

	beforeEach(() => {
		Element.prototype.scrollIntoView = vi.fn();
		main = document.createElement('main');
		main.scrollTo = vi.fn() as never;
		document.body.appendChild(main);
	});

	afterEach(async () => {
		cleanup();
		vi.useRealTimers();
		vi.restoreAllMocks();
		vi.resetAllMocks();
		pollers.length = 0;
		main.remove();
		window.location.hash = '';
		// Let the hashchange this reset fires land before the next test mounts.
		await settle();
		setTranscoderEnabled(true);
		setTranscodeRuntimeEnabled(true);
		writableOf<string>(theme).set('dark');
		writableOf<string>(colorScheme).set('default');
		writableOf<boolean>(schemeLocksMode).set(false);
		writableOf<unknown[]>(allSchemes).set([]);
	});

	describe('loading', () => {
		it('shows two skeleton cards and no tabs while settings load', () => {
			vi.mocked(fetchSettings).mockReturnValueOnce(new Promise(() => {}));
			renderComponent(SettingsPage);
			expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(2);
			expect(screen.queryAllByRole('tab')).toHaveLength(0);
		});

		it('shows the message of an Error thrown by the settings load', async () => {
			vi.mocked(fetchSettings).mockRejectedValueOnce(new Error('backend down'));
			renderComponent(SettingsPage);
			expect(await screen.findByText('Failed to load: backend down')).toBeInTheDocument();
			expect(screen.queryAllByRole('tab')).toHaveLength(0);
		});

		it('shows a generic message when the settings load throws a non-Error', async () => {
			vi.mocked(fetchSettings).mockRejectedValueOnce('nope');
			renderComponent(SettingsPage);
			expect(await screen.findByText('Failed to load: Failed to load settings')).toBeInTheDocument();
		});
	});

	describe('tab bar', () => {
		it('lists only the config groups the schema has, in this page order, then every screen tab', async () => {
			settingsOnce({ schema: schemaOf('Ripping', 'Identification', 'Transcoding') });
			await renderReady();
			expect(tabNames()).toEqual([
				'Identification',
				'Ripping',
				'Sessions',
				'Transcoding',
				'Notifications',
				'Interface',
				'Themes',
				'Drives',
				'Users',
				'System'
			]);
		});

		it('lists only the screen tabs when the settings carry no schema', async () => {
			settingsOnce({ schema: null });
			await renderReady();
			expect(tabNames()).toEqual([
				'Sessions',
				'Transcoding',
				'Notifications',
				'Interface',
				'Themes',
				'Drives',
				'Users',
				'System'
			]);
		});

		it('labels a config group by its label and a screen tab by its own label', async () => {
			await renderReady();
			expect(tab('API Keys')).toBeInTheDocument();
			expect(tab('Identification')).toBeInTheDocument();
			expect(screen.queryByRole('tab', { name: 'Keys' })).toBeNull();
			expect(tab('Users')).toBeInTheDocument();
		});

		it('clicking a tab selects it, sets the hash and scrolls main to the top', async () => {
			await renderReady();
			await fireEvent.click(tab('Themes'));
			expect(tab('Themes')).toHaveAttribute('aria-selected', 'true');
			expect(tab('Identification')).toHaveAttribute('aria-selected', 'false');
			expect(window.location.hash).toBe('#themes');
			expect(main.scrollTo).toHaveBeenCalledWith(0, 0);
		});

		it('does not run the hashchange work again for the hash a tab click set itself', async () => {
			await renderReady();
			await fireEvent.click(tab('Interface'));
			await settle();
			expect(main.scrollTo).toHaveBeenCalledTimes(1);
			expect(fetchImageCacheStats).toHaveBeenCalledTimes(1);
		});

		it('handles an external hash change after a tab click already consumed the programmatic flag', async () => {
			await renderReady();
			await fireEvent.click(tab('Themes'));
			await settle();
			window.location.hash = '#interface';
			await waitFor(() => expect(tab('Interface')).toHaveAttribute('aria-selected', 'true'));
			expect(main.scrollTo).toHaveBeenCalledTimes(2);
		});

		it('an external hash change switches the tab and runs that tab side effects', async () => {
			await renderReady();
			window.location.hash = '#interface';
			await waitFor(() => expect(tab('Interface')).toHaveAttribute('aria-selected', 'true'));
			expect(fetchImageCacheStats).toHaveBeenCalledTimes(1);
			expect(main.scrollTo).toHaveBeenCalledWith(0, 0);
			expect(screen.getByText('Image Cache')).toBeInTheDocument();
		});

		it('an external #drives hash loads the drive sessions and presets', async () => {
			await renderReady();
			window.location.hash = '#drives';
			await waitFor(() => expect(tab('Drives')).toHaveAttribute('aria-selected', 'true'));
			await waitFor(() => expect(fetchSessions).toHaveBeenCalledTimes(1));
			expect(fetchTranscodePresets).toHaveBeenCalledTimes(1);
		});

		it('an external hash with a field part sets the pending field and lands on its tab', async () => {
			await renderReady();
			window.location.hash = '#Keys/tmdb_api_key';
			await waitFor(() => expect(screen.getByLabelText(/tmdb api key/i)).toHaveFocus());
			expect(tab('API Keys')).toHaveAttribute('aria-selected', 'true');
		});

		it('falls back to Identification for an unknown hash', async () => {
			window.location.hash = '#bogus';
			await renderReady();
			expect(tab('Identification')).toHaveAttribute('aria-selected', 'true');
		});

		it('falls back to Identification when an external hash change names an unknown tab', async () => {
			await renderReady();
			await fireEvent.click(tab('Themes'));
			await settle();
			window.location.hash = '#bogus';
			await waitFor(() => expect(tab('Identification')).toHaveAttribute('aria-selected', 'true'));
		});

		it('maps the legacy #appearance and #Metadata hashes to Themes and Identification', async () => {
			window.location.hash = '#appearance';
			await renderReady();
			expect(tab('Themes')).toHaveAttribute('aria-selected', 'true');
			cleanup();
			window.location.hash = '#Metadata';
			await renderReady();
			expect(tab('Identification')).toHaveAttribute('aria-selected', 'true');
		});

		it('loads the image cache stats on first render when the hash opens Interface', async () => {
			window.location.hash = '#interface';
			await renderReady();
			await waitFor(() => expect(fetchImageCacheStats).toHaveBeenCalledTimes(1));
		});

		it('loads the drive sessions on first render when the hash opens Drives', async () => {
			window.location.hash = '#drives';
			await renderReady();
			await waitFor(() => expect(fetchSessions).toHaveBeenCalledTimes(1));
		});
	});

	describe('deep link #<tab>/<field>', () => {
		it('moves to the tab of the field own group, scrolls, focuses and highlights it, then drops the highlight after 1.6s', async () => {
			vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
			window.location.hash = '#Identification/tmdb_api_key';
			renderComponent(SettingsPage);
			await waitFor(() => expect(screen.getByLabelText(/tmdb api key/i)).toHaveFocus());
			expect(tab('API Keys')).toHaveAttribute('aria-selected', 'true');
			expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
			const el = screen.getByTestId('setting-tmdb_api_key');
			expect(el).toHaveClass('settings-field-highlight');
			await vi.advanceTimersByTimeAsync(1599);
			expect(el).toHaveClass('settings-field-highlight');
			await vi.advanceTimersByTimeAsync(1);
			expect(el).not.toHaveClass('settings-field-highlight');
		});

		it('decodes a URL-encoded field key', async () => {
			window.location.hash = '#Keys/tmdb%5Fapi%5Fkey';
			renderComponent(SettingsPage);
			await waitFor(() => expect(screen.getByLabelText(/tmdb api key/i)).toHaveFocus());
		});

		it('a key no group owns does nothing and is not retried on a later tab click', async () => {
			window.location.hash = '#Keys/ghost_key';
			await renderReady();
			expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
			expect(tab('API Keys')).toHaveAttribute('aria-selected', 'true');
			await fireEvent.click(tab('Ripping'));
			expect(tab('Ripping')).toHaveAttribute('aria-selected', 'true');
			expect(tab('API Keys')).toHaveAttribute('aria-selected', 'false');
		});

		it('a key whose group has no visible tab stays on the hash tab', async () => {
			settingsOnce({
				schema: { groups: [...mockSchema.groups, { name: 'Paths', fields: [field('raw_path', 'Paths')] }] }
			});
			window.location.hash = '#Ripping/raw_path';
			await renderReady();
			expect(tab('Ripping')).toHaveAttribute('aria-selected', 'true');
			expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
		});

		it('a field that never renders lands on its tab once and is not pulled back by a later tab click', async () => {
			window.location.hash = '#Keys/notifications_enabled';
			await renderReady();
			await waitFor(() => expect(tab('Notifications')).toHaveAttribute('aria-selected', 'true'));
			expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
			await fireEvent.click(tab('Ripping'));
			await settle();
			expect(tab('Ripping')).toHaveAttribute('aria-selected', 'true');
			expect(tab('Notifications')).toHaveAttribute('aria-selected', 'false');
		});
	});

	describe('Transcoding tab', () => {
		it('shows the ripper-only hint when the schema has no Transcoding group, even when capable', async () => {
			settingsOnce({ schema: schemaOf('Identification') });
			await openTab('Transcoding');
			expect(
				await screen.findByText('This deployment is ripper-only; transcoding cannot be enabled here.')
			).toBeInTheDocument();
			expect(screen.getByRole('switch', { name: 'Enable transcoding' })).toBeDisabled();
		});
	});

	describe('Notifications tab', () => {
		const master = () => screen.getByRole('switch', { name: /enable notifications/i });

		it('saves the master toggle on and shows the channels area', async () => {
			await openTab('Notifications');
			await fireEvent.click(master());
			await waitFor(() => expect(saveArmConfig).toHaveBeenCalledWith({ notifications_enabled: true }));
			expect(master()).toHaveAttribute('aria-checked', 'true');
			expect(screen.queryByText(/notifications are disabled/i)).toBeNull();
		});

		it('saves the master toggle off and shows the disabled hint', async () => {
			settingsOnce({ config: { ...mockConfig, notifications_enabled: true } });
			await openTab('Notifications');
			await waitFor(() => expect(master()).toHaveAttribute('aria-checked', 'true'));
			await fireEvent.click(master());
			await waitFor(() => expect(saveArmConfig).toHaveBeenCalledWith({ notifications_enabled: false }));
			expect(await screen.findByText(/notifications are disabled/i)).toBeInTheDocument();
			expect(master()).toHaveAttribute('aria-checked', 'false');
		});

		it('rolls the toggle back when the save fails', async () => {
			vi.mocked(saveArmConfig).mockRejectedValueOnce(new Error('save failed'));
			await openTab('Notifications');
			await fireEvent.click(master());
			await waitFor(() => expect(saveArmConfig).toHaveBeenCalledTimes(1));
			await waitFor(() => expect(master()).toHaveAttribute('aria-checked', 'false'));
			expect(screen.getByText(/notifications are disabled/i)).toBeInTheDocument();
		});

		it('ignores a second toggle while the first is still saving', async () => {
			const pending = deferred<{ success: boolean }>();
			vi.mocked(saveArmConfig).mockReturnValueOnce(pending.promise);
			await openTab('Notifications');
			await fireEvent.click(master());
			await waitFor(() => expect(master()).toHaveAttribute('aria-checked', 'true'));
			await fireEvent.click(master());
			expect(saveArmConfig).toHaveBeenCalledTimes(1);
			expect(master()).toHaveAttribute('aria-checked', 'true');
			pending.resolve({ success: true });
			await settle();
			expect(master()).toHaveAttribute('aria-checked', 'true');
		});
	});

	describe('Sessions and Users tabs', () => {
		it('renders the Sessions tab without the old routing card below the list', async () => {
			await openTab('Sessions');
			expect(tab('Sessions')).toHaveAttribute('aria-selected', 'true');
			expect(screen.queryByText('Session Routing')).not.toBeInTheDocument();
			expect(fetchSessionRoutes).not.toHaveBeenCalled();
		});

		it('renders the Users tab with its heading and the users card', async () => {
			await openTab('Users');
			expect(screen.getByRole('heading', { level: 2, name: 'Users' })).toBeInTheDocument();
			await waitFor(() => expect(fetchUsers).toHaveBeenCalled());
		});
	});

	describe('System tab', () => {
		const setupAgain = () => within(screen.getByTestId('run-setup-again')).getByRole('button');

		it('Run setup again shows Opening... while it runs, then goes to /setup/system and the button returns', async () => {
			const pending = deferred<never>();
			vi.mocked(restartSetup).mockReturnValueOnce(pending.promise);
			await openTab('System');
			expect(setupAgain()).toHaveTextContent('Run setup again');
			await fireEvent.click(setupAgain());
			expect(setupAgain()).toHaveTextContent('Opening...');
			expect(setupAgain()).toBeDisabled();
			expect(goto).not.toHaveBeenCalled();
			pending.resolve({} as never);
			await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/system'));
			await waitFor(() => expect(setupAgain()).toHaveTextContent('Run setup again'));
			expect(setupAgain()).not.toBeDisabled();
		});

		// Pins today's behaviour: a failed restart escapes the click handler as
		// an unhandled rejection and shows no error (#588). The test swaps in
		// its own listener so vitest does not fail the run on it, and puts
		// vitest's back afterwards.
		it('the button comes back after a failed restart, which does not navigate', async () => {
			const rejections: unknown[] = [];
			const previous = process.listeners('unhandledRejection');
			process.removeAllListeners('unhandledRejection');
			process.on('unhandledRejection', (r) => rejections.push(r));
			try {
				vi.mocked(restartSetup).mockRejectedValueOnce(new Error('restart failed'));
				await openTab('System');
				await fireEvent.click(setupAgain());
				await waitFor(() => expect(rejections).toHaveLength(1));
				expect((rejections[0] as Error).message).toBe('restart failed');
				expect(goto).not.toHaveBeenCalled();
				expect(setupAgain()).toHaveTextContent('Run setup again');
				expect(setupAgain()).not.toBeDisabled();
			} finally {
				process.removeAllListeners('unhandledRejection');
				previous.forEach((l) => process.on('unhandledRejection', l));
			}
		});

		it('lists the read-only configuration rows from the config value', async () => {
			settingsOnce({ config: { ...mockConfig, RAW_ROOT: '/from-config' } });
			await openTab('System');
			expect(screen.getByText('Configuration (read-only)')).toBeInTheDocument();
			expect(screen.getByTestId('setting-RAW_ROOT')).toHaveTextContent('/from-config');
		});

		it('falls back to settings.infra for a row the config does not carry', async () => {
			await openTab('System');
			expect(screen.getByTestId('setting-RAW_ROOT')).toHaveTextContent('/raw');
		});

		it('renders a row with no value when neither the config nor infra has it', async () => {
			settingsOnce({ infra: undefined });
			await openTab('System');
			expect(screen.getByTestId('setting-RAW_ROOT')).not.toHaveTextContent('/raw');
		});

		it('reads a null config as no value and falls back to infra', async () => {
			settingsOnce({ config: null, schema: schemaOf('System') });
			await openTab('System');
			expect(screen.getByTestId('setting-RAW_ROOT')).toHaveTextContent('/raw');
		});

		it('shows no configuration rows when the schema has no System group', async () => {
			settingsOnce({ schema: schemaOf('Identification') });
			await openTab('System');
			expect(screen.getByRole('heading', { level: 2, name: 'System' })).toBeInTheDocument();
			expect(screen.queryByText('Configuration (read-only)')).toBeNull();
			expect(screen.queryByTestId('setting-RAW_ROOT')).toBeNull();
		});
	});

	describe('Interface tab image cache', () => {
		const clearButton = () => screen.getByRole('button', { name: 'Clear Cache' });

		it('shows Loading... while the stats load', async () => {
			vi.mocked(fetchImageCacheStats).mockReturnValueOnce(new Promise(() => {}));
			await openTab('Interface');
			expect(screen.getByText('Loading...')).toBeInTheDocument();
		});

		it('shows the singular count', async () => {
			vi.mocked(fetchImageCacheStats).mockResolvedValueOnce({ count: 1, size_mb: '1.0' } as never);
			await openTab('Interface');
			expect(await screen.findByText(/1 cached image \(1\.0\s+MB\)/)).toBeInTheDocument();
			expect(clearButton()).not.toBeDisabled();
		});

		it('shows the plural count', async () => {
			await openTab('Interface');
			expect(await screen.findByText(/5 cached images \(5\.0\s+MB\)/)).toBeInTheDocument();
		});

		it('says it is unable to load the stats when they fail, and disables Clear Cache', async () => {
			vi.mocked(fetchImageCacheStats).mockRejectedValueOnce(new Error('no stats'));
			await openTab('Interface');
			expect(await screen.findByText('Unable to load cache stats')).toBeInTheDocument();
			expect(clearButton()).toBeDisabled();
		});

		it('disables Clear Cache when the cache holds zero images', async () => {
			vi.mocked(fetchImageCacheStats).mockResolvedValueOnce({ count: 0, size_mb: '0.0' } as never);
			await openTab('Interface');
			expect(await screen.findByText(/0 cached images/)).toBeInTheDocument();
			expect(clearButton()).toBeDisabled();
		});

		it('the confirm dialog Cancel closes it without clearing', async () => {
			await openTab('Interface');
			await screen.findByText(/5 cached images/);
			await fireEvent.click(clearButton());
			const dialog = screen.getByRole('dialog');
			expect(dialog).toHaveTextContent('Clear Image Cache');
			await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
			expect(screen.queryByRole('dialog')).toBeNull();
			expect(clearImageCache).not.toHaveBeenCalled();
		});

		async function clearWith(result: unknown) {
			vi.mocked(clearImageCache).mockResolvedValueOnce(result as never);
			await openTab('Interface');
			await screen.findByText(/cached images?/);
			await fireEvent.click(clearButton());
			await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear' }));
		}

		it('a clear of one image reports it singular with the freed MB and reloads the stats', async () => {
			vi.mocked(fetchImageCacheStats)
				.mockResolvedValueOnce({ count: 1, size_mb: '1.0' } as never)
				.mockResolvedValueOnce({ count: 0, size_mb: '0.0' } as never);
			await clearWith({ cleared: 1, freed_bytes: 1048576 });
			const feedback = await screen.findByText('Cleared 1 cached image (1.0 MB)');
			expect(feedback).toHaveAttribute('data-error', 'false');
			expect(fetchImageCacheStats).toHaveBeenCalledTimes(2);
			expect(await screen.findByText(/0 cached images/)).toBeInTheDocument();
			expect(screen.queryByRole('dialog')).toBeNull();
		});

		it('a clear of several images reports them plural', async () => {
			await clearWith({ cleared: 3, freed_bytes: 2621440 });
			expect(await screen.findByText('Cleared 3 cached images (2.5 MB)')).toBeInTheDocument();
		});

		it('missing cleared and freed_bytes count as 0', async () => {
			await clearWith({ success: true });
			expect(await screen.findByText('Cleared 0 cached images (0.0 MB)')).toBeInTheDocument();
		});

		it('a failed clear shows the Error message', async () => {
			vi.mocked(clearImageCache).mockRejectedValueOnce(new Error('disk busy'));
			await openTab('Interface');
			await screen.findByText(/5 cached images/);
			await fireEvent.click(clearButton());
			await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear' }));
			const feedback = await screen.findByText('disk busy');
			expect(feedback).toHaveAttribute('data-error', 'true');
			expect(clearButton()).not.toBeDisabled();
		});

		it('a failed clear with a non-Error shows a generic message', async () => {
			vi.mocked(clearImageCache).mockRejectedValueOnce('nope');
			await openTab('Interface');
			await screen.findByText(/5 cached images/);
			await fireEvent.click(clearButton());
			await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear' }));
			expect(await screen.findByText('Failed to clear cache')).toBeInTheDocument();
		});

		it('reloads the stats each time the tab is opened by a click', async () => {
			await openTab('Interface');
			await screen.findByText(/5 cached images/);
			await fireEvent.click(tab('Ripping'));
			await fireEvent.click(tab('Interface'));
			await waitFor(() => expect(fetchImageCacheStats).toHaveBeenCalledTimes(2));
		});

		it('reloads the stats each time the tab is opened by the hash', async () => {
			await openTab('Interface');
			await screen.findByText(/5 cached images/);
			await fireEvent.click(tab('Ripping'));
			await settle();
			window.location.hash = '#interface';
			await waitFor(() => expect(fetchImageCacheStats).toHaveBeenCalledTimes(2));
		});
	});

	describe('Themes tab', () => {
		const schemes = [
			{ id: 'blue', label: 'Blue', swatch: '#00f', builtin: true, description: 'A calm blue' },
			{ id: 'red', label: 'Red', swatch: '#f00' },
			{ id: 'mine', label: 'Mine', swatch: '#0f0', builtin: false, author: 'Ann' },
			{ id: 'solo', label: 'Solo', swatch: '#ff0', builtin: false }
		];
		const swatch = (label: string) => screen.getByText(label).closest('button') as HTMLButtonElement;
		const deleteButtons = () => screen.getAllByTitle('Delete');

		beforeEach(() => {
			writableOf<unknown[]>(allSchemes).set(schemes);
			vi.spyOn(window, 'confirm').mockReturnValue(true);
		});

		it('lists the built-in swatches with their descriptions and selects one on click', async () => {
			await openTab('Themes');
			expect(screen.getByText('A calm blue')).toBeInTheDocument();
			expect(swatch('Blue')).toHaveAttribute('data-selected', 'false');
			await fireEvent.click(swatch('Red'));
			expect(get(colorScheme)).toBe('red');
			expect(swatch('Red')).toHaveAttribute('data-selected', 'true');
		});

		it('lists the user themes with and without an author, and selects one on click', async () => {
			await openTab('Themes');
			expect(screen.getByRole('heading', { level: 3, name: 'User Themes' })).toBeInTheDocument();
			expect(screen.getByText('by Ann')).toBeInTheDocument();
			expect(screen.getAllByText(/^by /)).toHaveLength(1);
			await fireEvent.click(swatch('Mine'));
			expect(get(colorScheme)).toBe('mine');
		});

		it('hides the User Themes card when there are no user themes', async () => {
			writableOf<unknown[]>(allSchemes).set(schemes.slice(0, 2));
			await openTab('Themes');
			expect(screen.queryByRole('heading', { name: 'User Themes' })).toBeNull();
			expect(screen.queryAllByTitle('Delete')).toHaveLength(0);
		});

		it('does nothing when the delete confirm is declined', async () => {
			vi.mocked(window.confirm).mockReturnValue(false);
			await openTab('Themes');
			await fireEvent.click(deleteButtons()[0]);
			expect(window.confirm).toHaveBeenCalledWith('Delete user theme "Mine"?');
			expect(deleteTheme).not.toHaveBeenCalled();
			expect(loadThemesFromApi).not.toHaveBeenCalled();
			expect(screen.queryByText(/deleted/)).toBeNull();
		});

		// The feedback shows twice, at the top and under the user themes (#541).
		it('a delete reloads the themes and shows its success feedback in both places', async () => {
			writableOf<string>(colorScheme).set('red');
			await openTab('Themes');
			await fireEvent.click(deleteButtons()[0]);
			await waitFor(() => expect(deleteTheme).toHaveBeenCalledWith('mine'));
			expect(loadThemesFromApi).toHaveBeenCalledTimes(1);
			const feedback = await screen.findAllByText('Theme "Mine" deleted');
			expect(feedback).toHaveLength(2);
			expect(feedback[0]).toHaveClass('alert-success');
			expect(feedback[1]).toHaveAttribute('data-error', 'false');
			expect(get(colorScheme)).toBe('red');
		});

		it('deleting the active theme falls back to blue', async () => {
			writableOf<string>(colorScheme).set('solo');
			await openTab('Themes');
			await fireEvent.click(deleteButtons()[1]);
			await waitFor(() => expect(deleteTheme).toHaveBeenCalledWith('solo'));
			await screen.findAllByText('Theme "Solo" deleted');
			expect(get(colorScheme)).toBe('blue');
		});

		it('a failed delete shows the Error message in both places', async () => {
			vi.mocked(deleteTheme).mockRejectedValueOnce(new Error('in use'));
			await openTab('Themes');
			await fireEvent.click(deleteButtons()[0]);
			const feedback = await screen.findAllByText('in use');
			expect(feedback).toHaveLength(2);
			expect(feedback[0]).toHaveClass('alert-danger');
			expect(feedback[1]).toHaveAttribute('data-error', 'true');
			expect(loadThemesFromApi).not.toHaveBeenCalled();
		});

		it('a failed delete with a non-Error shows a generic message', async () => {
			vi.mocked(deleteTheme).mockRejectedValueOnce('nope');
			await openTab('Themes');
			await fireEvent.click(deleteButtons()[0]);
			expect(await screen.findAllByText('Delete failed')).toHaveLength(2);
		});

		it('shows dark mode on', async () => {
			await openTab('Themes');
			expect(screen.getByRole('switch', { name: 'Dark mode' })).toHaveAttribute('aria-checked', 'true');
			expect(screen.getByText('On')).toHaveAttribute('data-on', 'true');
		});

		it('shows dark mode off', async () => {
			writableOf<string>(theme).set('light');
			await openTab('Themes');
			expect(screen.getByRole('switch', { name: 'Dark mode' })).toHaveAttribute('aria-checked', 'false');
			expect(screen.getByText('Off')).toHaveAttribute('data-on', 'false');
		});

		it('shows no dark mode switch when the scheme locks the mode', async () => {
			writableOf<boolean>(schemeLocksMode).set(true);
			await openTab('Themes');
			expect(screen.getByText('Locked by theme')).toBeInTheDocument();
			expect(screen.queryByRole('switch', { name: 'Dark mode' })).toBeNull();
		});
	});

	describe('Drives tab', () => {
		const session = (over: Record<string, unknown>) => ({
			id: 's',
			name: 'S',
			media_type: 'movie',
			is_builtin: false,
			rip_preset_id: 'rp',
			transcode_preset_id: null,
			output_path_template: '',
			overrides_json: {},
			...over
		});

		it('shows the polling error as an alert instead of the drive lists', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([
				drive({ id: 'drv_enrolled', display_name: 'Main Drive' }),
				drive({ id: 'drv_detected', lifecycle: 'detected' })
			]);
			await openTab('Drives');
			await screen.findByText('Main Drive');
			lastPoller().error.set('Drive service unreachable');
			expect(await screen.findByText('Drive service unreachable')).toHaveClass('alert-danger');
			expect(screen.queryByText('Main Drive')).toBeNull();
			expect(screen.queryByTestId('drive-lifecycle-panel')).toBeNull();
		});

		it('an enrolled card takes the prescan defaults from arm_config', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			settingsOnce({
				arm_config: {
					PRESCAN_CACHE_MB: '64',
					PRESCAN_TIMEOUT: '600',
					PRESCAN_RETRIES: '5',
					DISC_ENUM_TIMEOUT: '120'
				}
			});
			await openTab('Drives');
			await screen.findByText('Main Drive');
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByLabelText(/Pre-scan Cache/)).toHaveAttribute('placeholder', '64');
			expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '600');
			expect(screen.getByLabelText(/Pre-scan Retries/)).toHaveAttribute('placeholder', '5');
			expect(screen.getByLabelText(/Enum Timeout/)).toHaveAttribute('placeholder', '120');
			expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Auto)');
		});

		it('an enrolled card falls back to the built-in prescan defaults and a manual global rip mode', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			settingsOnce({ config: { ...mockConfig, auto_rip_on_insert: false } });
			await openTab('Drives');
			await screen.findByText('Main Drive');
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByLabelText(/Pre-scan Cache/)).toHaveAttribute('placeholder', '1');
			expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '300');
			expect(screen.getByLabelText(/Pre-scan Retries/)).toHaveAttribute('placeholder', '3');
			expect(screen.getByLabelText(/Enum Timeout/)).toHaveAttribute('placeholder', '60');
			expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Manual)');
		});

		it('shows no card grid when no drive is enrolled', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([drive({ id: 'drv_detected', lifecycle: 'detected' })]);
			await openTab('Drives');
			await screen.findByTestId('detected-row-drv_detected');
			expect(screen.queryByTestId('drive-card-essentials')).toBeNull();
		});

		it('a card update refreshes the drive list', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			await openTab('Drives');
			await screen.findByText('Main Drive');
			const before = lastPoller().refresh.mock.calls.length;
			await fireEvent.change(screen.getByRole('combobox', { name: 'Rip mode' }), { target: { value: 'manual' } });
			await waitFor(() => expect(updateDrive).toHaveBeenCalledWith('drv_1', { drive_mode: 'manual' }));
			await waitFor(() => expect(lastPoller().refresh.mock.calls).toHaveLength(before + 1));
		});

		it('a lifecycle change refreshes the drive list', async () => {
			vi.mocked(fetchDrives).mockResolvedValue([drive({ id: 'drv_detected', lifecycle: 'detected' })]);
			await openTab('Drives');
			await fireEvent.click(await screen.findByTestId('enroll-drv_detected'));
			await waitFor(() => expect(enrollDrive).toHaveBeenCalledWith('drv_detected'));
			await waitFor(() => expect(lastPoller().refresh).toHaveBeenCalledTimes(1));
		});

		it('a rescan refreshes the drive list', async () => {
			await openTab('Drives');
			await fireEvent.click(screen.getByTestId('drive-rescan'));
			await waitFor(() => expect(rescanDrives).toHaveBeenLastCalledWith(false));
			await waitFor(() => expect(lastPoller().refresh).toHaveBeenCalledTimes(1));
		});

		it('starts polling even when the initial rescan fails', async () => {
			vi.mocked(rescanDrives).mockRejectedValueOnce(new Error('rescan failed'));
			vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			await openTab('Drives');
			expect(await screen.findByText('Main Drive')).toBeInTheDocument();
			expect(lastPoller().start).toHaveBeenCalledTimes(1);
		});

		it('fetches the drive sessions once: a second visit does not refetch', async () => {
			vi.mocked(fetchSessions).mockResolvedValue([session({ id: 's1', name: 'Movie rip' })] as never);
			vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			await openTab('Drives');
			expect(await screen.findByRole('option', { name: 'Movie rip' })).toBeInTheDocument();
			expect(fetchSessions).toHaveBeenCalledTimes(1);
			await fireEvent.click(tab('Ripping'));
			await fireEvent.click(tab('Drives'));
			await screen.findByText('Main Drive');
			expect(fetchSessions).toHaveBeenCalledTimes(1);
			expect(fetchTranscodePresets).toHaveBeenCalledTimes(1);
		});

		describe('on a ripper-only deployment', () => {
			const sessions = [
				session({ id: 's_plain', name: 'Plain rip' }),
				session({ id: 's_pass', name: 'Passthrough rip', transcode_preset_id: 'p_none' }),
				session({ id: 's_enc', name: 'Encode rip', transcode_preset_id: 'p_enc' })
			];
			const presets = [
				{ id: 'p_none', tool: 'none' },
				{ id: 'p_enc', tool: 'handbrake' }
			];
			const optionNames = () => screen.getAllByRole('option').map((o) => o.textContent);

			beforeEach(() => {
				setTranscoderEnabled(false);
				vi.mocked(fetchDrives).mockResolvedValue([drive({ display_name: 'Main Drive' })]);
			});

			it('offers passthrough sessions only, judged by the fetched presets', async () => {
				vi.mocked(fetchSessions).mockResolvedValue(sessions as never);
				vi.mocked(fetchTranscodePresets).mockResolvedValue(presets as never);
				await openTab('Drives');
				await screen.findByRole('option', { name: 'Passthrough rip' });
				expect(optionNames()).toContain('Plain rip');
				expect(optionNames()).not.toContain('Encode rip');
			});

			it('a failed preset fetch hides the preset-backed sessions but keeps the sessions', async () => {
				vi.mocked(fetchSessions).mockResolvedValue(sessions as never);
				vi.mocked(fetchTranscodePresets).mockRejectedValue(new Error('presets down'));
				await openTab('Drives');
				await screen.findByRole('option', { name: 'Plain rip' });
				expect(optionNames()).not.toContain('Passthrough rip');
				expect(optionNames()).not.toContain('Encode rip');
			});

			it('a failed session fetch leaves the picker empty without losing the presets fetch', async () => {
				vi.mocked(fetchSessions).mockRejectedValue(new Error('sessions down'));
				vi.mocked(fetchTranscodePresets).mockResolvedValue(presets as never);
				await openTab('Drives');
				await screen.findByText('Main Drive');
				await waitFor(() => expect(fetchTranscodePresets).toHaveBeenCalledTimes(1));
				expect(optionNames()).not.toContain('Plain rip');
			});
		});
	});

	describe('Drive diagnostics', () => {
		const diag = (over: Record<string, unknown> = {}) => ({
			id: 'drv_a',
			lifecycle: 'enrolled',
			present: true,
			identity_kind: 'by_id',
			device_path: '/dev/sr0',
			status: null,
			media_status: null,
			media_status_at: null,
			container: null,
			last_error: null,
			healthy: true,
			notes: [],
			...over
		});
		const toggle = () => screen.getByRole('button', { name: /Drive Diagnostics/ });
		const runCheck = () => screen.getByRole('button', { name: /Run Check|Running/ });

		async function openAndRun(response: unknown) {
			vi.mocked(fetchDriveDiagnostic).mockResolvedValueOnce(response as never);
			await openTab('Drives');
			await fireEvent.click(toggle());
			await fireEvent.click(runCheck());
		}

		it('opens and closes the panel, with the Run Check hint before any run', async () => {
			await openTab('Drives');
			expect(toggle()).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(toggle());
			expect(toggle()).toHaveAttribute('aria-expanded', 'true');
			expect(runCheck()).toBeInTheDocument();
			expect(screen.getByText('Click "Run Check" to scan drives and udev configuration.')).toBeInTheDocument();
			expect(screen.queryByText(/Last run:/)).toBeNull();
			await fireEvent.click(toggle());
			expect(toggle()).toHaveAttribute('aria-expanded', 'false');
		});

		it('shows the last run time after a successful run', async () => {
			await openAndRun({ drives: [diag()], system: [] });
			expect(await screen.findByText(/Last run:/)).toBeInTheDocument();
			expect(screen.queryByText(/Click "Run Check"/)).toBeNull();
		});

		it('shows Running... without the hint while a run is pending, and ignores a second click', async () => {
			const pending = deferred<never>();
			vi.mocked(fetchDriveDiagnostic).mockReturnValueOnce(pending.promise);
			await openTab('Drives');
			await fireEvent.click(toggle());
			await fireEvent.click(runCheck());
			expect(runCheck()).toHaveTextContent('Running...');
			expect(runCheck()).toBeDisabled();
			expect(screen.queryByText(/Click "Run Check"/)).toBeNull();
			await fireEvent.click(runCheck());
			expect(fetchDriveDiagnostic).toHaveBeenCalledTimes(1);
			pending.resolve({ drives: [diag()], system: [] } as never);
			expect(await screen.findByText('All OK')).toBeInTheDocument();
			expect(runCheck()).toHaveTextContent('Run Check');
		});

		it('shows the Error message when a run fails, and clears the previous result', async () => {
			await openAndRun({ drives: [diag()], system: [] });
			await screen.findByText('All OK');
			vi.mocked(fetchDriveDiagnostic).mockRejectedValueOnce(new Error('udev unavailable'));
			await fireEvent.click(runCheck());
			expect(await screen.findByText('udev unavailable')).toBeInTheDocument();
			expect(screen.queryByText('All OK')).toBeNull();
			expect(screen.getByText(/Click "Run Check"/)).toBeInTheDocument();
		});

		it('shows a generic message when a run fails with a non-Error', async () => {
			vi.mocked(fetchDriveDiagnostic).mockRejectedValueOnce('nope');
			await openTab('Drives');
			await fireEvent.click(toggle());
			await fireEvent.click(runCheck());
			expect(await screen.findByText('Diagnostic failed')).toBeInTheDocument();
		});

		it('shows the system notes, Issues Found and the singular drive count', async () => {
			await openAndRun({ drives: [diag()], system: ['ripper manager is not running'] });
			const notes = await screen.findByTestId('diag-system');
			expect(notes).toHaveTextContent('ripper manager is not running');
			expect(screen.getByText('Issues Found').closest('.alert')).toHaveClass('alert-warning');
			expect(screen.getByText('1 drive')).toBeInTheDocument();
		});

		it('shows All OK with the plural drive count and no system notes when the response has no system list', async () => {
			await openAndRun({ drives: [diag(), diag({ id: 'drv_b', device_path: '/dev/sr1' })] });
			expect(await screen.findByText('All OK')).toBeInTheDocument();
			expect(screen.getByText('All OK').closest('.alert')).toHaveClass('alert-success');
			expect(screen.getByText('2 drives')).toBeInTheDocument();
			expect(screen.queryByTestId('diag-system')).toBeNull();
		});

		it('lists every per-drive field of a connected drive', async () => {
			await openAndRun({
				drives: [
					diag({
						container: 'running',
						status: 'online',
						media_status: 'tray_open',
						media_status_at: '2026-09-05T01:36:29Z',
						last_error: 'SCSI NOT_READY'
					})
				],
				system: []
			});
			const row = await screen.findByTestId('diag-drive-drv_a');
			expect(row).toHaveTextContent('/dev/sr0');
			expect(row).toHaveTextContent('enrolled');
			expect(row).toHaveTextContent('connected');
			expect(row).toHaveTextContent('container: running');
			expect(row).toHaveTextContent('ripper: online');
			expect(row).toHaveTextContent('media: tray open');
			expect(row).toHaveTextContent(/heartbeat \S+/);
			expect(row).toHaveTextContent('SCSI NOT_READY');
			expect(row).toHaveTextContent('OK');
			expect(row).toHaveAttribute('data-flagged', 'false');
		});

		it('omits the optional fields a drive does not report', async () => {
			await openAndRun({ drives: [diag({ present: false, healthy: false })], system: [] });
			const row = await screen.findByTestId('diag-drive-drv_a');
			expect(row).toHaveTextContent('not connected');
			for (const text of ['container:', 'ripper:', 'media:', 'heartbeat']) {
				expect(row).not.toHaveTextContent(text);
			}
		});

		it('shows the ignored note and a healthy drive informational notes as plain text', async () => {
			await openAndRun({
				drives: [diag({ lifecycle: 'ignored', notes: ['ignored', 'identified by port'] })],
				system: []
			});
			const row = await screen.findByTestId('diag-drive-drv_a');
			expect(within(row).getByText('ignored', { selector: 'span.settings-page-diag-ignored' })).toBeInTheDocument();
			expect(within(row).getByText('identified by port')).toHaveClass('settings-page-diag-ignored');
			expect(screen.getByText('All OK')).toBeInTheDocument();
		});

		it('flags an unhealthy drive and shows its notes as warnings', async () => {
			await openAndRun({
				drives: [diag({ healthy: false, notes: ['drive is detached'] })],
				system: []
			});
			const row = await screen.findByTestId('diag-drive-drv_a');
			expect(row).toHaveAttribute('data-flagged', 'true');
			expect(within(row).getByText('drive is detached')).toHaveClass('settings-page-diag-warn-text');
			expect(within(row).queryByText('unhealthy')).toBeNull();
			expect(screen.getByText('Issues Found')).toBeInTheDocument();
		});

		it('shows unhealthy for an unhealthy drive that has no notes', async () => {
			await openAndRun({ drives: [diag({ healthy: false, notes: [] })], system: [] });
			const row = await screen.findByTestId('diag-drive-drv_a');
			expect(within(row).getByText('unhealthy')).toBeInTheDocument();
			expect(within(row).queryByText('OK')).toBeNull();
		});
	});
});
