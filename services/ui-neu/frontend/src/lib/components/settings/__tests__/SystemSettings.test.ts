import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/testing/render';
import SystemSettings from '../SystemSettings.svelte';
import { SetupRestart } from '$lib/stores/setup-restart.svelte';
import { goto } from '$app/navigation';
import { restartSetup } from '$lib/api/setup';
import { fetchSystemDiagnostics, fetchSystemEnvironment } from '$lib/api/system';
import { ApiError } from '$lib/api/client';
import { fetchDiagnostics } from '$lib/api/diagnostics';

// Branches not forced here: the `?? ''` fallbacks Svelte compiles around the
// expressions in the summary line (`{env.version}`, `{yesNo(...)}`): version is
// a required string and yesNo always returns a string, so none is ever nullish.

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

const health = { status: 'ok', checks: [{ name: 'config', status: 'ok', detail: null }], paths: [] };

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

function stubClipboard(): ReturnType<typeof vi.fn> {
	const writeText = vi.fn((_text: string) => Promise.resolve());
	Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
	return writeText;
}

async function copyReport(writeText: ReturnType<typeof vi.fn>): Promise<string> {
	await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
	await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
	return writeText.mock.calls[0][0] as string;
}

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
		if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard);
		else delete (navigator as unknown as Record<string, unknown>).clipboard;
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

	it('explains an admin-only environment to a guest instead of erroring, and hides the copy button', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce(
			new ApiError(403, 'read-only role: write access required', null)
		);
		vi.mocked(fetchDiagnostics).mockResolvedValueOnce({ services: [{ name: 'arm-ripper', log_level: 'INFO' }] });
		renderSystem();
		expect(await screen.findByTestId('environment-forbidden')).toHaveTextContent(/admins only/);
		expect(screen.queryByTestId('environment-error')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Copy deployment report' })).not.toBeInTheDocument();
		expect(screen.getByTestId('diag-level-arm-ripper')).toHaveTextContent('INFO');
	});

	it('tells the user what the report contains beside the copy button', () => {
		renderSystem();
		expect(screen.getByTestId('report-sharing-notice')).toHaveTextContent(
			'Review this report before you share it publicly: it shows host paths, usernames, hostnames, LAN addresses, drive serials and file names. Edit out anything you do not want to share.'
		);
	});

	it('drops the sharing notice with the copy button for a guest', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce(new ApiError(403, 'forbidden', null));
		renderSystem();
		await screen.findByTestId('environment-forbidden');
		expect(screen.queryByTestId('report-sharing-notice')).not.toBeInTheDocument();
	});

	it('copies a report from the loaded environment and the health result of the last system check', async () => {
		vi.mocked(fetchSystemDiagnostics).mockResolvedValueOnce(health);
		const writeText = stubClipboard();
		renderSystem();
		await screen.findByTestId('system-summary');
		await fireEvent.click(screen.getByRole('button', { name: 'Run system check' }));
		await waitFor(() => expect(fetchSystemDiagnostics).toHaveBeenCalledTimes(1));
		const report = await copyReport(writeText);
		expect(report).toContain('## ARM deployment report | 3.1.0');
		expect(report).toContain('- PASS');
		expect(fetchSystemEnvironment).toHaveBeenCalledTimes(1);
		expect(fetchSystemDiagnostics).toHaveBeenCalledTimes(1);
	});

	it('fetches the environment and health on copy when neither loaded', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce(new Error('env down'));
		vi.mocked(fetchSystemDiagnostics).mockResolvedValueOnce(health);
		const writeText = stubClipboard();
		renderSystem();
		await screen.findByTestId('environment-error');
		const report = await copyReport(writeText);
		expect(report).toContain('## ARM deployment report | 3.1.0');
		expect(report).toContain('### Health');
		expect(fetchSystemEnvironment).toHaveBeenCalledTimes(2);
		expect(fetchSystemDiagnostics).toHaveBeenCalledTimes(1);
	});

	it('summarises unknown host paths and no GPUs', async () => {
		vi.mocked(fetchSystemEnvironment).mockResolvedValueOnce({
			version: '3.1.0',
			summary: { host_paths_set: null, transcode_capable: true, gpus: [] },
			groups: [],
			containers: []
		});
		renderSystem();
		const summary = await screen.findByTestId('system-summary');
		expect(summary).toHaveTextContent('Host paths set: unknown');
		expect(summary).toHaveTextContent('Transcode capable: yes');
		expect(summary).toHaveTextContent('GPUs: none');
	});

	it('falls back to a generic environment error for a non-Error rejection', async () => {
		vi.mocked(fetchSystemEnvironment).mockRejectedValueOnce('boom');
		renderSystem();
		expect(await screen.findByTestId('environment-error')).toHaveTextContent('Failed to load the environment');
	});
});
