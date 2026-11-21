import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/test-utils';
import SystemSettings from '../SystemSettings.svelte';
import { SetupRestart } from '$lib/stores/setupRestart.svelte';
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';
import { fetchSystemEnvironment } from '$lib/api/system';
import { fetchDiagnostics } from '$lib/api/diagnostics';
import type { SettingsData } from '$lib/api/settings';
import type { SettingsGroup } from '$lib/types/api.gen';

vi.mock('$app/navigation', async (importOriginal) => ({
	...(await importOriginal<Record<string, unknown>>()),
	goto: vi.fn()
}));

vi.mock('$lib/api/setup', () => ({
	restartSetup: vi.fn(() => Promise.resolve({}))
}));

// SystemHealth and DiagnosticsSection fetch on mount; their calls are faked
// so the component renders without a network.
vi.mock('$lib/api/system', () => ({
	fetchSystemDiagnostics: vi.fn(() => Promise.reject(new Error('checks unavailable'))),
	fetchSystemEnvironment: vi.fn(() =>
		Promise.resolve({
			version: '3.1.0',
			summary: { host_paths_set: true, transcode_capable: false, gpus: ['nvidia'] },
			groups: [{ name: 'Paths', vars: [] }],
			containers: [
				{
					kind: 'ripper',
					label: 'arm-ripper',
					state: 'running',
					image: 'arm',
					network: null,
					docker_host: null,
					mounts: [],
					devices: [],
					env: []
				}
			]
		})
	),
	fetchSystemVersion: vi.fn()
}));

vi.mock('$lib/api/resources', () => ({
	fetchResources: vi.fn(() => Promise.reject(new Error('resources unavailable')))
}));

vi.mock('$lib/api/diagnostics', () => ({
	fetchDiagnostics: vi.fn(() => Promise.resolve({ services: [] }))
}));

function field(key: string, label: string) {
	return {
		key,
		group: 'System',
		tier: 'infra',
		label,
		help: '',
		type: 'string',
		editable: false,
		enum_values: null
	};
}

const group = {
	name: 'System',
	fields: [field('RAW_ROOT', 'Raw root'), field('DB_URL', 'Database url')]
} as unknown as SettingsGroup;

function settingsData(over: Record<string, unknown> = {}): SettingsData {
	return {
		config: { RAW_ROOT: '/from-config' },
		schema: { groups: [group] },
		infra: { RAW_ROOT: '/from-infra', DB_URL: 'postgres://db' },
		arm_config: {},
		transcoder_config: null,
		...over
	} as unknown as SettingsData;
}

function renderSystem(over: { settings?: SettingsData; group?: SettingsGroup; setup?: SetupRestart } = {}) {
	const setup = over.setup ?? new SetupRestart();
	renderComponent(SystemSettings, {
		props: {
			settings: over.settings ?? settingsData(),
			group: 'group' in over ? over.group : group,
			setup
		}
	});
	return setup;
}

describe('SystemSettings', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		cleanup();
	});

	it('renders the System heading and the Setup walkthrough card', () => {
		renderSystem();
		expect(screen.getByRole('heading', { name: 'System' })).toBeInTheDocument();
		const card = screen.getByTestId('run-setup-again');
		expect(within(card).getByRole('heading', { name: 'Setup walkthrough' })).toBeInTheDocument();
		expect(within(card).getByText(/Your current values are kept/)).toBeInTheDocument();
	});

	it('labels the restart button "Run setup again" and enables it when idle', () => {
		renderSystem();
		expect(screen.getByRole('button', { name: 'Run setup again' })).toBeEnabled();
	});

	it('runs the setup restart when the button is clicked', async () => {
		renderSystem();
		await fireEvent.click(screen.getByRole('button', { name: 'Run setup again' }));
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/system'));
		expect(restartSetup).toHaveBeenCalledTimes(1);
	});

	it('shows "Opening..." and disables the button while the restart is running', () => {
		const setup = new SetupRestart();
		setup.running = true;
		renderSystem({ setup });
		const button = screen.getByRole('button', { name: 'Opening...' });
		expect(button).toBeDisabled();
		expect(screen.queryByRole('button', { name: 'Run setup again' })).not.toBeInTheDocument();
	});

	it('does not render the old Configuration block', () => {
		renderSystem();
		expect(screen.queryByText('Configuration (read-only)')).not.toBeInTheDocument();
		expect(screen.queryByTestId('setting-RAW_ROOT')).not.toBeInTheDocument();
	});

	it('keeps only operator-tier System fields in a read-only Operator settings block', () => {
		const g = {
			name: 'System',
			fields: [field('RAW_ROOT', 'Raw root'), { ...field('drive_scan_interval_seconds', 'Scan'), tier: 'operator' }]
		} as unknown as SettingsGroup;
		renderSystem({ group: g });
		expect(screen.getByRole('heading', { name: 'Operator settings' })).toBeInTheDocument();
		expect(screen.getByTestId('setting-drive_scan_interval_seconds')).toBeInTheDocument();
		expect(screen.queryByTestId('setting-RAW_ROOT')).not.toBeInTheDocument();
	});

	it('omits Operator settings when there are none', () => {
		renderSystem();
		expect(screen.queryByTestId('operator-settings')).not.toBeInTheDocument();
	});

	it('orders summary, health, environment, containers, setup walkthrough', async () => {
		renderSystem();
		await screen.findByTestId('environment-section');
		const ids = [
			'system-summary',
			'system-health-block',
			'environment-section',
			'containers-section',
			'run-setup-again'
		];
		const els = ids.map((id) => screen.getByTestId(id));
		for (let i = 1; i < els.length; i++) {
			expect(els[i - 1].compareDocumentPosition(els[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		}
		expect(screen.getByTestId('system-summary')).toHaveTextContent('Version 3.1.0');
		expect(screen.getByRole('button', { name: 'Copy deployment report' })).toBeInTheDocument();
	});

	it('shows a log-level load error', async () => {
		vi.mocked(fetchDiagnostics).mockRejectedValueOnce(new Error('nope'));
		renderSystem();
		expect(await screen.findByTestId('log-levels-error')).toHaveTextContent('Failed to load log levels');
	});

	it('still shows log levels when the environment fails', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce(new Error('env down'));
		vi.mocked(fetchDiagnostics).mockResolvedValueOnce({ services: [{ name: 'arm-ripper', log_level: 'INFO' }] });
		renderSystem();
		expect(await screen.findByTestId('diag-level-arm-ripper')).toHaveTextContent('INFO');
	});

	it('shows the environment load error', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce(new Error('env down'));
		renderSystem();
		expect(await screen.findByTestId('environment-error')).toHaveTextContent('env down');
	});
});
