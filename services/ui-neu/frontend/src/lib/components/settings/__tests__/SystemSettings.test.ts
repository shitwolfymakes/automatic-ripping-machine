import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/testing/render';
import SystemSettings from '../SystemSettings.svelte';
import { SetupRestart } from '$lib/stores/setup-restart.svelte';
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';
import { fetchSystemEnvironment } from '$lib/api/system';
import { fetchDiagnostics } from '$lib/api/diagnostics';

vi.mock('$app/navigation', async (importOriginal) => ({
	...(await importOriginal<Record<string, unknown>>()),
	goto: vi.fn()
}));

vi.mock('$lib/api/setup', () => ({
	restartSetup: vi.fn(() => Promise.resolve({}))
}));

// SystemHealth and the environment section fetch on mount; their calls are faked
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

function renderSystem(over: { setup?: SetupRestart } = {}) {
	const setup = over.setup ?? new SetupRestart();
	renderComponent(SystemSettings, { props: { setup } });
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

	it('heads the health checks and their run button with Diagnostics', () => {
		renderSystem();
		const block = screen.getByTestId('system-health-block');
		expect(within(block).getByRole('heading', { name: 'Diagnostics' })).toBeInTheDocument();
		expect(block).toHaveAccessibleName('Diagnostics');
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

	it('renders no settings fields (the drive scanner tunables live on the Drives tab)', () => {
		renderSystem();
		expect(screen.queryByText('Configuration (read-only)')).not.toBeInTheDocument();
		expect(screen.queryByText('Operator settings')).not.toBeInTheDocument();
		expect(screen.queryByTestId('setting-drive_scan_interval_seconds')).not.toBeInTheDocument();
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
