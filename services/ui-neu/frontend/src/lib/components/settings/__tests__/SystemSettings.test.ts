import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/test-utils';
import SystemSettings from '../SystemSettings.svelte';
import { SetupRestart } from '$lib/stores/setup-restart.svelte';
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';
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

	it('omits the Configuration list when there is no group', () => {
		renderSystem({ group: undefined });
		expect(screen.queryByText('Configuration (read-only)')).not.toBeInTheDocument();
		expect(screen.queryByTestId('setting-RAW_ROOT')).not.toBeInTheDocument();
	});

	it('lists each group field in the Configuration list when a group is given', () => {
		renderSystem();
		expect(screen.getByRole('heading', { name: 'Configuration (read-only)' })).toBeInTheDocument();
		expect(screen.getByTestId('setting-RAW_ROOT')).toBeInTheDocument();
		expect(screen.getByTestId('setting-DB_URL')).toBeInTheDocument();
	});

	it('reads a field value from settings.config when the key is present', () => {
		renderSystem();
		expect(within(screen.getByTestId('setting-RAW_ROOT')).getByText('/from-config')).toBeInTheDocument();
	});

	it('reads a field value from settings.infra when settings.config lacks the key', () => {
		renderSystem();
		expect(within(screen.getByTestId('setting-DB_URL')).getByText('postgres://db')).toBeInTheDocument();
	});

	it('reads field values from settings.infra when settings.config is absent', () => {
		renderSystem({ settings: settingsData({ config: undefined }) });
		expect(within(screen.getByTestId('setting-RAW_ROOT')).getByText('/from-infra')).toBeInTheDocument();
	});

	it('renders the Diagnostics section', () => {
		renderSystem();
		expect(screen.getByRole('heading', { name: 'Diagnostics' })).toBeInTheDocument();
	});
});
