import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import SettingsPage from '../+page.svelte';
import { fetchSettings } from '$lib/api/settings';
import { fetchDrives, fetchDriveDiagnostic } from '$lib/api/drives';
import type { DriveView } from '$lib/types/api.gen';

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1', hostname: 'arm-ripper-abc', device_path: '/dev/sr0', display_name: null, status: 'online',
		last_seen_at: null, media_status: null, media_status_at: null, default_session_id: null, rip_speed: null,
		drive_mode: null, uhd_capable: null, prescan_cache_mb: null, prescan_timeout: null, prescan_retries: null,
		disc_enum_timeout: null, created_at: null, updated_at: null, lifecycle: 'enrolled', present: true,
		identity_kind: 'by_id', serial: 'AAAABBBB000E', by_id_name: 'usb-X_AAAABBBB000E-0:0', vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX', last_error: null, current_job: null, ...over
	} as DriveView;
}

// Per-test override of the fetchSettings mock with a custom config patch.
function withConfig(patch: Record<string, unknown>) {
	vi.mocked(fetchSettings).mockResolvedValueOnce({
		config: { ...mockConfig, ...patch },
		schema: mockSchema,
		infra: { RAW_ROOT: '/raw' },
		arm_config: {},
		transcoder_config: null
	} as never);
}

// New schema-driven config shape. The page reads `settings.config` (values),
// `settings.schema.groups` (structure → tabs + fields), and `settings.infra`
// (System read-only values). The dead v2 ARM_* blob / abcde / transcoder-config
// / systemInfo surface is gone.
const mockSchema = {
	groups: [
		{
			name: 'Metadata',
			fields: [
				{ key: 'metadata_provider', group: 'Metadata', tier: 'operator', label: 'Metadata provider', help: '', type: 'enum', editable: true, enum_values: ['tmdb', 'omdb'] },
				{ key: 'tmdb_api_key', group: 'Metadata', tier: 'secret', label: 'TMDb API key', help: '', type: 'string', editable: true, enum_values: null }
			]
		},
		{
			name: 'Ripping',
			fields: [
				{ key: 'auto_rip_on_insert', group: 'Ripping', tier: 'operator', label: 'Auto-rip on insert', help: '', type: 'bool', editable: true, enum_values: null },
				{ key: 'block_on_miss', group: 'Ripping', tier: 'operator', label: 'Block on miss', help: '', type: 'bool', editable: true, enum_values: null }
			]
		},
		{
			name: 'Transcoding',
			fields: [
				{ key: 'auto_transcode_on_idle', group: 'Transcoding', tier: 'operator', label: 'Auto-transcode on idle', help: '', type: 'bool', editable: true, enum_values: null }
			]
		},
		{
			name: 'Notifications',
			fields: [
				{ key: 'notifications_enabled', group: 'Notifications', tier: 'operator', label: 'Enable notifications', help: '', type: 'bool', editable: true, enum_values: null }
			]
		},
		{
			name: 'System',
			fields: [
				{ key: 'RAW_ROOT', group: 'System', tier: 'infra', label: 'Raw root', help: '', type: 'string', editable: false, enum_values: null }
			]
		}
	]
};

const mockConfig = {
	metadata_provider: 'omdb',
	tmdb_api_key: '<hidden>',
	auto_rip_on_insert: true,
	block_on_miss: true,
	auto_transcode_on_idle: false,
	notifications_enabled: false
};

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
	// SchemaConfigForm imports saveArmConfig for the Save button.
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
	rescanDrives: vi.fn(() => Promise.resolve({ online: 0, stale: 0, detected: 0, enrolled: 0, ignored: 0, absent: 0, pruned: 0 }))
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

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/colorScheme', async () => {
	const { writable } = await import('svelte/store');
	return {
		colorScheme: writable('default'),
		COLOR_SCHEMES: [{ id: 'default', label: 'Default', swatch: '#3b82f6', tokens: {}, mode: 'dark' }],
		schemeLocksMode: writable(false),
		allSchemes: writable([{ id: 'default', label: 'Default', swatch: '#3b82f6', tokens: {}, mode: 'dark' }]),
		loadThemesFromApi: vi.fn()
	};
});

vi.mock('$lib/api/maintenance', () => ({
	fetchImageCacheStats: vi.fn(() => Promise.resolve({ count: 5, size_bytes: 5242880, size_mb: '5.0' })),
	clearImageCache: vi.fn(() => Promise.resolve({ success: true, cleared: 5, freed_bytes: 5242880 }))
}));

vi.mock('$lib/api/channels', () => ({
	fetchChannels: vi.fn(() =>
		Promise.resolve([
			{
				id: 1,
				type: 'apprise',
				name: 'Family Discord',
				enabled: true,
				config: { type: 'apprise', url: 'discord://a/b' },
				subscribed_events: ['job.started'],
				templates: {},
				last_fired_at: null,
				last_success_at: null,
				last_error: null
			}
		])
	),
	fetchServices: vi.fn(() =>
		Promise.resolve({
			featured: ['discord'],
			services: [{ id: 'discord', name: 'Discord', docs_url: '', url_scheme: 'discord', required_fields: [], advanced_fields: [] }]
		})
	),
	fetchEventTypes: vi.fn(() =>
		Promise.resolve([
			{
				key: 'rip.completed',
				label: 'Rip completed',
				variables: ['job_title', 'drive_id'],
				default_title: 'ARM: rip completed — {job_title}',
				default_body: '{job_title} finished ripping on drive {drive_id}.'
			}
		])
	),
	fetchDispatches: vi.fn(() => Promise.resolve([])),
	createChannel: vi.fn(() => Promise.resolve({ id: 2 })),
	updateChannel: vi.fn(() => Promise.resolve({ id: 1 })),
	deleteChannel: vi.fn(() => Promise.resolve({})),
	testSendChannel: vi.fn(() => Promise.resolve({ ok: true, error: null })),
	composeUrl: vi.fn(() => Promise.resolve({ url: 'discord://a/b' })),
	testConfig: vi.fn(() => Promise.resolve({ ok: true, error: null }))
}));

vi.mock('$lib/stores/polling', async () => {
	const { writable } = await import('svelte/store');
	return {
		// A minimal fake that actually calls the fetcher on start()/refresh(),
		// so tests can assert on data that flows from e.g. fetchDrives.
		createPollingStore: vi.fn((fetcher: () => Promise<unknown>, initialValue: unknown) => {
			const data = writable(initialValue);
			async function load() {
				try {
					data.set(await fetcher());
				} catch {
					// ignore — tests that care about errors use the error store directly
				}
			}
			return {
				subscribe: data.subscribe,
				data,
				loading: writable(false),
				error: writable(null),
				initialized: writable(true),
				refresh: vi.fn(load),
				start: vi.fn(load),
				stop: vi.fn()
			};
		})
	};
});

describe('Settings Page', () => {
	afterEach(() => {
		cleanup();
		// Tab clicks write window.location.hash; jsdom persists it across tests,
		// which would leave the next render on a non-default tab. Reset so each
		// test starts on the default Metadata tab.
		window.location.hash = '';
	});

	// Render the page and wait for the tab bar to settle. Metadata is the
	// default tab; its config form renders the provider <select> once settings
	// load, which is the readiness signal. ("Metadata" text appears in both the
	// tab button and the form heading, so it isn't a unique signal.)
	async function renderAndWait() {
		renderComponent(SettingsPage);
		await waitFor(() => {
			expect(screen.getByRole('combobox', { name: /metadata provider/i })).toBeInTheDocument();
		});
	}

	// Render, then switch to a top-level tab by its label.
	async function renderAndOpenTab(tab: string) {
		await renderAndWait();
		await fireEvent.click(screen.getAllByText(tab)[0]);
	}

	describe('rendering', () => {
		it('renders the Interface tab with the stats toggle and dashboard layout', async () => {
			await renderAndOpenTab('Interface');
			expect(screen.getByRole('switch', { name: /show resource stats/i })).toBeInTheDocument();
			expect(screen.getByRole('radio', { name: /cards/i })).toBeInTheDocument();
			expect(screen.getByRole('radio', { name: /table/i })).toBeInTheDocument();
		});

		it('maps a legacy #appearance hash to the Themes tab', async () => {
			window.location.hash = '#appearance';
			renderComponent(SettingsPage);
			await waitFor(() => {
				expect(screen.getByText('Image Cache')).toBeInTheDocument();
			});
		});

		it('renders page title', () => {
			renderComponent(SettingsPage);
			expect(screen.getByText('Settings')).toBeInTheDocument();
		});

		it('deep-links #<tab>/<field> to the field: scrolls, focuses and highlights it', async () => {
			window.location.hash = '#Metadata/tmdb_api_key';
			const scrollIntoView = vi.fn();
			Element.prototype.scrollIntoView = scrollIntoView;
			await renderAndWait();
			await waitFor(() => {
				expect(screen.getByLabelText(/tmdb api key/i)).toHaveFocus();
			});
			expect(scrollIntoView).toHaveBeenCalled();
			expect(screen.getByTestId('setting-tmdb_api_key').className).toContain('ring-2');
		});

		it('renders the Metadata config tab with the provider select', async () => {
			await renderAndWait();
			// Metadata is the default tab — its SchemaConfigForm renders the enum field.
			expect(screen.getByRole('combobox', { name: /metadata provider/i })).toBeInTheDocument();
		});

		it('renders the Ripping config tab', async () => {
			await renderAndWait();
			await fireEvent.click(screen.getByRole('button', { name: 'Ripping' }));
			await waitFor(() => expect(screen.getByRole('checkbox', { name: /auto-rip on insert/i })).toBeInTheDocument());
		});

		it('does not render a Music tab', async () => {
			await renderAndWait();
			expect(screen.queryByText('Music')).not.toBeInTheDocument();
		});

		it('renders a Sessions tab', async () => {
			await renderAndWait();
			expect(screen.getByRole('button', { name: 'Sessions' })).toBeInTheDocument();
		});

		it('does not render a Rip Presets tab', async () => {
			await renderAndWait();
			expect(screen.queryByRole('button', { name: 'Rip Presets' })).not.toBeInTheDocument();
		});

		it('does not render a Transcode Presets tab', async () => {
			await renderAndWait();
			expect(screen.queryByRole('button', { name: 'Transcode Presets' })).not.toBeInTheDocument();
		});

		it('shows Themes tab', async () => {
			await renderAndWait();
			const matches = screen.getAllByText('Themes');
			expect(matches.length).toBeGreaterThanOrEqual(1);
		});

		it('image cache section loads when Themes tab active', async () => {
			await renderAndOpenTab('Themes');
			await waitFor(() => {
				expect(screen.getByText('Image Cache')).toBeInTheDocument();
			});
			// Verify cache stats are rendered
			await waitFor(() => {
				expect(screen.getByText(/5 cached images/)).toBeInTheDocument();
				expect(screen.getByText(/5\.0 MB/)).toBeInTheDocument();
			});
			// Verify Clear Cache button exists
			expect(screen.getByText('Clear Cache')).toBeInTheDocument();
		});

		it('shows cache feedback after clearing image cache', async () => {
			await renderAndOpenTab('Themes');
			await waitFor(() => {
				expect(screen.getByText('Clear Cache')).toBeInTheDocument();
			});
			// Click Clear Cache to open confirm dialog
			await fireEvent.click(screen.getByText('Clear Cache'));
			// Confirm the dialog — confirmLabel is "Clear"
			await waitFor(() => {
				expect(screen.getByText('Clear Image Cache')).toBeInTheDocument();
			});
			const clearBtns = screen.getAllByText('Clear');
			await fireEvent.click(clearBtns[clearBtns.length - 1]);
			// Verify feedback message appears
			await waitFor(() => {
				expect(screen.getByText(/Cleared 5 cached images/)).toBeInTheDocument();
			});
		});

		it('shows dark mode toggle when scheme does not lock mode', async () => {
			await renderAndOpenTab('Themes');
			await waitFor(() => {
				expect(screen.getByText('Dark Mode')).toBeInTheDocument();
			});
			expect(screen.getByLabelText('Dark mode')).toBeInTheDocument();
			expect(screen.getByText('Toggle between light and dark mode.')).toBeInTheDocument();
		});

		it('calls toggleTheme when dark mode switch is clicked', async () => {
			const { toggleTheme } = await import('$lib/stores/theme');
			await renderAndOpenTab('Themes');
			await waitFor(() => {
				expect(screen.getByLabelText('Dark mode')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByLabelText('Dark mode'));
			expect(toggleTheme).toHaveBeenCalled();
		});

		it('shows "Locked by theme" when schemeLocksMode is true', async () => {
			const { schemeLocksMode } = await import('$lib/stores/colorScheme');
			const { writable } = await import('svelte/store');
			const locked = writable(true);
			Object.assign(schemeLocksMode, { set: locked.set, subscribe: locked.subscribe, update: locked.update });

			await renderAndOpenTab('Themes');
			await waitFor(() => {
				expect(screen.getByText('Locked by theme')).toBeInTheDocument();
			});
			expect(screen.queryByLabelText('Dark mode')).not.toBeInTheDocument();
		});

		it('notifications tab renders the channels UI when notifications are enabled', async () => {
			withConfig({ notifications_enabled: true });
			await renderAndOpenTab('Notifications');
			// Channels UI is gated on the master toggle (enabled here).
			await waitFor(() => expect(screen.getByText('Family Discord')).toBeInTheDocument());
			expect(screen.getByRole('button', { name: /add channel/i })).toBeInTheDocument();
			expect(screen.getByText('Channels')).toBeInTheDocument();
		});

		it('hides the channels UI and shows a hint when notifications are disabled', async () => {
			// default mockConfig has notifications_enabled: false
			await renderAndOpenTab('Notifications');
			await waitFor(() =>
				expect(screen.getByText(/notifications are disabled/i)).toBeInTheDocument()
			);
			expect(screen.queryByText('Family Discord')).not.toBeInTheDocument();
			// the master toggle (a switch, not a checkbox — auto-saves, no Save button)
			expect(screen.getByRole('switch', { name: /enable notifications/i })).toBeInTheDocument();
		});

		it('master toggle auto-saves on click (no Save button)', async () => {
			const { saveArmConfig } = await import('$lib/api/settings');
			await renderAndOpenTab('Notifications');
			await waitFor(() =>
				expect(screen.getByRole('switch', { name: /enable notifications/i })).toBeInTheDocument()
			);
			await fireEvent.click(screen.getByRole('switch', { name: /enable notifications/i }));
			await waitFor(() =>
				expect(vi.mocked(saveArmConfig)).toHaveBeenCalledWith({ notifications_enabled: true })
			);
			// the channels UI appears immediately (optimistic) without a Save action
			await waitFor(() => expect(screen.getByText('Family Discord')).toBeInTheDocument());
		});

		it('renders drives tab with collapsible diagnostics toggle', async () => {
			await renderAndOpenTab('Drives');
			await waitFor(() => {
				expect(screen.getByText('Udev & Drive Diagnostics')).toBeInTheDocument();
			});
			// Run Check button should not be visible when collapsed
			expect(screen.queryByText('Run Check')).not.toBeInTheDocument();
		});

		it('renders enrolled cards, detected/ignored lists, and maintenance buttons', async () => {
			vi.mocked(fetchDrives).mockResolvedValueOnce([
				drive({ id: 'drv_enrolled', lifecycle: 'enrolled', display_name: 'Main Drive' }),
				drive({ id: 'drv_detected', lifecycle: 'detected' }),
				drive({ id: 'drv_ignored', lifecycle: 'ignored' })
			]);
			await renderAndOpenTab('Drives');
			await waitFor(() => expect(screen.getByText('Main Drive')).toBeInTheDocument());
			expect(screen.getByTestId('detected-row-drv_detected')).toBeInTheDocument();
			expect(screen.getByTestId('ignored-toggle')).toBeInTheDocument();
			expect(screen.getByTestId('drive-rescan')).toBeInTheDocument();
			expect(screen.getByTestId('drive-force-rescan')).toBeInTheDocument();
		});

		it('diagnostics panel renders system notes and per-drive fields, with Issues Found', async () => {
			vi.mocked(fetchDriveDiagnostic).mockResolvedValueOnce({
				drives: [
					{
						id: 'drv_1',
						lifecycle: 'enrolled',
						present: false,
						identity_kind: 'by_id',
						device_path: '/dev/sr0',
						status: 'offline',
						media_status: 'detached',
						media_status_at: null,
						container: 'running',
						last_error: null,
						healthy: false,
						notes: ['drive is detached: reconnect it']
					}
				],
				system: ['ripper manager is not running: enroll is unavailable']
			});
			await renderAndOpenTab('Drives');
			await waitFor(() => {
				expect(screen.getByText('Udev & Drive Diagnostics')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Udev & Drive Diagnostics'));
			await fireEvent.click(screen.getByText('Run Check'));
			await waitFor(() => {
				expect(screen.getByText('ripper manager is not running: enroll is unavailable')).toBeInTheDocument();
			});
			expect(screen.getByText(/drive is detached: reconnect it/)).toBeInTheDocument();
			expect(screen.getByText('Issues Found')).toBeInTheDocument();
		});

		it('diagnostics panel lists a healthy drive with its details and All OK', async () => {
			vi.mocked(fetchDriveDiagnostic).mockResolvedValueOnce({
				drives: [
					{
						id: 'drv_ok',
						lifecycle: 'enrolled',
						present: true,
						identity_kind: 'by_id',
						device_path: '/dev/sr2',
						status: 'online',
						media_status: 'tray_open',
						media_status_at: '2026-09-05T01:36:29Z',
						container: 'running',
						last_error: null,
						healthy: true,
						notes: []
					}
				],
				system: []
			});
			await renderAndOpenTab('Drives');
			await waitFor(() => {
				expect(screen.getByText('Udev & Drive Diagnostics')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Udev & Drive Diagnostics'));
			await fireEvent.click(screen.getByText('Run Check'));
			await waitFor(() => {
				expect(screen.getByText('All OK')).toBeInTheDocument();
			});
			const row = screen.getByTestId('diag-drive-drv_ok');
			expect(row).toHaveTextContent('/dev/sr2');
			expect(row).toHaveTextContent('enrolled');
			expect(row).toHaveTextContent('connected');
			expect(row).toHaveTextContent('container: running');
			expect(row).toHaveTextContent('media: tray open');
			expect(row).toHaveTextContent('OK');
		});
	});
});
