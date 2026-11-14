import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import SystemHealth from '../SystemHealth.svelte';

// Branch pins for SystemHealth, beside SystemHealth.test.ts. Nothing here
// forces a branch the component cannot reach; no branch is left open.

const fetchSystemDiagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({ fetchSystemDiagnostics: () => fetchSystemDiagnostics() }));
const fetchResources = vi.fn();
vi.mock('$lib/api/resources', () => ({ fetchResources: () => fetchResources() }));

const mediaStorage = { name: 'MEDIA_ROOT', path: '/media', total_gb: 1000, used_gb: 249, free_gb: 751 };

type Check = Record<string, unknown>;
type Path = Record<string, unknown>;
const diagnostics = (checks: Check[], paths: Path[] = []) => ({ status: 'ok', checks, paths });
const okPath = (over: Path = {}) => ({ name: 'MEDIA_ROOT', path: '/media', exists: true, writable: true, ...over });

async function renderGrouped(checks: Check[], paths: Path[] = [], scope: 'all' | 'system' = 'all') {
	fetchSystemDiagnostics.mockResolvedValue(diagnostics(checks, paths));
	renderComponent(SystemHealth, { props: { autorun: true, grouped: true, scope } });
	await screen.findByTestId('system-health-summary');
}

async function renderList(checks: Check[], paths: Path[] = []) {
	fetchSystemDiagnostics.mockResolvedValue(diagnostics(checks, paths));
	renderComponent(SystemHealth);
	await fireEvent.click(screen.getByTestId('system-health-run'));
	await screen.findByTestId('system-health-summary');
}

beforeEach(() => fetchResources.mockResolvedValue({ storage: [mediaStorage] }));
afterEach(() => {
	cleanup();
	fetchSystemDiagnostics.mockReset();
	fetchResources.mockReset();
});

describe('SystemHealth labels', () => {
	it('shows an unlabelled path name itself, with an empty help line', async () => {
		await renderGrouped([], [okPath({ name: 'SCRATCH_ROOT', path: '/scratch' })]);
		const row = screen.getByTestId('system-health-path');
		expect(within(row).getByText('SCRATCH_ROOT')).toBeInTheDocument();
		expect(within(row).queryByText('Media library')).toBeNull();
		expect(within(row).queryByText('Finished files are filed here.')).toBeNull();
	});

	it('shows an unlabelled check name itself in the other checks panel', async () => {
		await renderGrouped([{ name: 'mystery_check', status: 'ok', detail: null }]);
		expect(screen.getByText('mystery_check')).toBeInTheDocument();
	});

	it('shows an unlabelled check name itself in the list layout', async () => {
		await renderList([{ name: 'mystery_check', status: 'ok', detail: null }]);
		expect(screen.getByText('mystery_check')).toBeInTheDocument();
	});
});

describe('SystemHealth services', () => {
	it('gives a status other than ok or error the warning badge', async () => {
		await renderGrouped([{ name: 'transcoder', status: 'unknown', detail: null, location: 'local' }]);
		const row = screen.getByTestId('system-health-service');
		expect(row).toHaveAttribute('data-status', 'unknown');
		expect(within(row).getByText('Problem')).toBeInTheDocument();
		expect(within(row).getByText(/Encode containers can't start right now/)).toBeInTheDocument();
	});

	it('names a remote transcoder with no host just "Remote host"', async () => {
		await renderGrouped([{ name: 'transcoder', status: 'ok', detail: null, location: 'remote', remote_host: null }]);
		const row = screen.getByTestId('system-health-service');
		expect(within(row).getByText('Remote host')).toBeInTheDocument();
		expect(within(row).getByText('Encode containers can run.')).toBeInTheDocument();
	});

	it('shows no location chip and no detail chips for a service without them', async () => {
		await renderGrouped([{ name: 'ripper_manager', status: 'ok', detail: null }]);
		const row = screen.getByTestId('system-health-service');
		expect(within(row).getByText('ARM can start a ripper for each drive you enroll.')).toBeInTheDocument();
		expect(within(row).queryByText('This server')).toBeNull();
		expect(within(row).queryByText(/Ripper only/)).toBeNull();
		expect(within(row).queryByText(/Remote host/)).toBeNull();
	});

	it('gives the ripper-only transcoder its own description and chip', async () => {
		await renderGrouped([{ name: 'transcoder', status: 'warning', detail: null, location: 'none' }]);
		const row = screen.getByTestId('system-health-service');
		expect(
			within(row).getByText('This install only rips; encoding happens elsewhere or not at all.')
		).toBeInTheDocument();
		expect(within(row).getByText('Ripper only')).toBeInTheDocument();
	});

	it('marks a failed detail chip as a problem and a passing one as plain', async () => {
		await renderGrouped([
			{
				name: 'transcoder',
				status: 'ok',
				detail: null,
				location: 'local',
				details: [
					{ label: 'Docker socket', ok: true },
					{ label: 'Transcode image', ok: false }
				]
			}
		]);
		const row = screen.getByTestId('system-health-service');
		expect(within(row).getByText('Docker socket')).toBeInTheDocument();
		expect(within(row).getByText('Transcode image: problem')).toBeInTheDocument();
	});

	it('shows a service detail line only when it is not ok and has a detail', async () => {
		await renderGrouped([
			{ name: 'ripper_manager', status: 'error', detail: 'docker socket unavailable' },
			{ name: 'transcoder', status: 'ok', detail: 'fine but chatty', location: 'local' }
		]);
		expect(screen.getByText('docker socket unavailable')).toBeInTheDocument();
		expect(screen.queryByText('fine but chatty')).toBeNull();
	});

	it('shows no detail line for a failing service with no detail', async () => {
		await renderGrouped([{ name: 'ripper_manager', status: 'error', detail: null }]);
		const row = screen.getByTestId('system-health-service');
		expect(within(row).getByText(/can't start a ripper for your drives/)).toBeInTheDocument();
		expect(within(row).queryByText('null')).toBeNull();
	});
});

describe('SystemHealth storage', () => {
	it('gives a path that exists but is not writable the warning state, with the chown command', async () => {
		await renderGrouped([], [okPath({ writable: false, host_path: '/srv/media', uid: 1, gid: 2 })]);
		const row = screen.getByTestId('system-health-path');
		expect(row).toHaveAttribute('data-status', 'warning');
		expect(within(row).getByText('Not writable')).toBeInTheDocument();
		expect(within(row).getByText('sudo chown -R 1:2 /srv/media')).toBeInTheDocument();
	});

	it('points a path with no host path at the .env setting', async () => {
		await renderGrouped([], [okPath({ exists: false, writable: false })]);
		const row = screen.getByTestId('system-health-path');
		expect(row).toHaveAttribute('data-status', 'error');
		expect(within(row).getByText('Missing')).toBeInTheDocument();
		expect(within(row).getByText(/Set ARM_HOST_\*_PATH in .env/)).toBeInTheDocument();
		expect(within(row).queryByText(/sudo chown/)).toBeNull();
	});

	it('shows Measuring... for a path whose root storage did not report', async () => {
		fetchResources.mockResolvedValue({ storage: [mediaStorage] });
		await renderGrouped([], [okPath({ name: 'RAW_ROOT', path: '/raw' })]);
		await waitFor(() => expect(fetchResources).toHaveBeenCalled());
		expect(screen.getByText('Measuring...')).toBeInTheDocument();
	});

	it('shows Measuring... when the storage call fails', async () => {
		fetchResources.mockRejectedValue(new Error('503'));
		await renderGrouped([], [okPath()]);
		await waitFor(() => expect(fetchResources).toHaveBeenCalled());
		expect(screen.getByText('Measuring...')).toBeInTheDocument();
	});

	it('shows Measuring... until storage loads, then the free space', async () => {
		let release: (v: unknown) => void = () => {};
		fetchResources.mockReturnValue(new Promise((r) => (release = r)));
		await renderGrouped([], [okPath()]);
		expect(screen.getByText('Measuring...')).toBeInTheDocument();
		release({ storage: [mediaStorage] });
		expect(await screen.findByText('751 GB free')).toBeInTheDocument();
	});
});

describe('SystemHealth checks', () => {
	it('shows "Health checks failed" when the rejection is not an Error', async () => {
		fetchSystemDiagnostics.mockRejectedValue('boom');
		renderComponent(SystemHealth);
		await fireEvent.click(screen.getByTestId('system-health-run'));
		expect(await screen.findByTestId('system-health-error')).toHaveTextContent('Health checks failed');
	});

	it('shows the error in the grouped layout too, and still looks up storage', async () => {
		fetchSystemDiagnostics.mockRejectedValue(new Error('API 503'));
		renderComponent(SystemHealth, { props: { autorun: true, grouped: true } });
		expect(await screen.findByTestId('system-health-error')).toHaveTextContent('API 503');
		await waitFor(() => expect(fetchResources).toHaveBeenCalled());
	});

	it('shows OK for an ok check with no detail and the status for another one', async () => {
		await renderList([
			{ name: 'config', status: 'ok', detail: null },
			{ name: 'drives', status: 'warning', detail: null }
		]);
		const [ok, warn] = screen.getAllByTestId('system-health-check');
		expect(within(ok).getByText('OK')).toBeInTheDocument();
		expect(within(warn).getByText('warning')).toBeInTheDocument();
	});

	it('shows the same fallbacks in the grouped other checks panel', async () => {
		await renderGrouped([
			{ name: 'config', status: 'ok', detail: null },
			{ name: 'drives', status: 'warning', detail: null }
		]);
		const [ok, warn] = screen.getAllByTestId('system-health-check');
		expect(within(ok).getByText('OK')).toBeInTheDocument();
		expect(within(warn).getByText('warning')).toBeInTheDocument();
	});

	it('shows the other checks panel in the system scope only when one is not ok', async () => {
		await renderGrouped([{ name: 'config', status: 'ok', detail: null }], [], 'system');
		expect(screen.queryByText('Other checks')).toBeNull();
		cleanup();
		await renderGrouped([{ name: 'config', status: 'error', detail: 'bad' }], [], 'system');
		expect(screen.getByText('Other checks')).toBeInTheDocument();
		expect(screen.getByText('bad')).toBeInTheDocument();
	});

	it('hides the other checks panel when there are none', async () => {
		await renderGrouped([{ name: 'transcoder', status: 'ok', detail: null, location: 'local' }]);
		expect(screen.queryByText('Other checks')).toBeNull();
	});

	it('counts one issue as "1 issue found" in the list layout', async () => {
		await renderList([{ name: 'drives', status: 'warning', detail: 'none' }], [okPath()]);
		expect(screen.getByTestId('system-health-summary')).toHaveTextContent('1 issue found');
	});

	it('words each path state in the list layout', async () => {
		await renderList(
			[],
			[
				okPath({ name: 'A', path: '/a' }),
				okPath({ name: 'B', path: '/b', writable: false }),
				okPath({ name: 'C', path: '/c', exists: false, writable: false })
			]
		);
		const rows = screen.getAllByTestId('system-health-path');
		expect(rows[0]).toHaveTextContent('/a, writable');
		expect(rows[1]).toHaveTextContent('/b, not writable');
		expect(rows[2]).toHaveTextContent('/c, missing');
	});
});
