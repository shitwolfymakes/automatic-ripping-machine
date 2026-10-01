import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SystemHealth from '../SystemHealth.svelte';

const fetchSystemDiagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({ fetchSystemDiagnostics: () => fetchSystemDiagnostics() }));
const fetchResources = vi.fn(() =>
	Promise.resolve({ storage: [{ name: 'MEDIA_ROOT', path: '/media', total_gb: 1000, used_gb: 249, free_gb: 751 }] })
);
vi.mock('$lib/api/resources', () => ({ fetchResources: () => fetchResources() }));

afterEach(() => {
	cleanup();
	fetchSystemDiagnostics.mockReset();
});

describe('SystemHealth', () => {
	it('runs GET /api/system/diagnostics on click and lists every check with its detail', async () => {
		fetchSystemDiagnostics.mockResolvedValue({
			status: 'ok',
			checks: [
				{ name: 'config', status: 'ok', detail: null },
				{ name: 'makemkv_key', status: 'ok', detail: 'MakeMKV key is valid' },
				{ name: 'ripper_manager', status: 'ok', detail: null }
			],
			paths: [{ name: 'MEDIA_ROOT', path: '/media', exists: true, writable: true }]
		});
		renderComponent(SystemHealth);
		await fireEvent.click(screen.getByTestId('system-health-run'));
		await waitFor(() => expect(screen.getByTestId('system-health-summary')).toHaveTextContent('All OK'));
		expect(screen.getAllByTestId('system-health-check')).toHaveLength(3);
		expect(screen.getByText('MakeMKV key')).toBeInTheDocument();
		expect(screen.getByText('MakeMKV key is valid')).toBeInTheDocument();
		expect(screen.getByText('Ripper manager')).toBeInTheDocument();
		expect(screen.getByTestId('system-health-path')).toHaveTextContent('/media');
	});

	it('counts warnings, errors and bad paths as issues', async () => {
		fetchSystemDiagnostics.mockResolvedValue({
			status: 'error',
			checks: [
				{ name: 'transcoder', status: 'warning', detail: 'transcoder not configured' },
				{ name: 'makemkv_key', status: 'error', detail: 'key invalid' }
			],
			paths: [{ name: 'RAW_ROOT', path: '/raw', exists: true, writable: false }]
		});
		renderComponent(SystemHealth);
		await fireEvent.click(screen.getByTestId('system-health-run'));
		await waitFor(() => expect(screen.getByTestId('system-health-summary')).toHaveTextContent('3 issues found'));
		expect(screen.getByTestId('system-health-path')).toHaveAttribute('data-status', 'warning');
		expect(screen.getByTestId('system-health-path')).toHaveTextContent('not writable');
	});

	it('shows the error when the request fails', async () => {
		fetchSystemDiagnostics.mockRejectedValue(new Error('API 503: Service Unavailable'));
		renderComponent(SystemHealth);
		await fireEvent.click(screen.getByTestId('system-health-run'));
		await waitFor(() => expect(screen.getByTestId('system-health-error')).toHaveTextContent('API 503'));
	});
});

describe('SystemHealth grouped (setup walkthrough + Settings > System)', () => {
	const problem = {
		status: 'error',
		checks: [
			{ name: 'config', status: 'ok', detail: null },
			{ name: 'MEDIA_ROOT', status: 'error', detail: '/media: exists=True writable=False' },
			{ name: 'drives', status: 'warning', detail: 'no online drives registered' },
			{
				name: 'ripper_manager',
				status: 'warning',
				detail: 'permission denied on /var/run/docker.sock',
				details: [{ label: 'Docker socket', ok: false, message: 'permission denied on /var/run/docker.sock' }]
			},
			{
				name: 'transcoder',
				status: 'ok',
				detail: null,
				location: 'local',
				details: [
					{ label: 'Docker socket', ok: true },
					{ label: 'Transcode image', ok: true }
				]
			}
		],
		paths: [
			{
				name: 'MEDIA_ROOT',
				path: '/media',
				exists: true,
				writable: false,
				host_path: '/home/me/arm/media',
				uid: 1000,
				gid: 1000
			},
			{
				name: 'RAW_ROOT',
				path: '/raw',
				exists: true,
				writable: true,
				host_path: '/home/me/arm/raw',
				uid: 1000,
				gid: 1000
			}
		]
	};

	it('autoruns and reports the result', async () => {
		fetchSystemDiagnostics.mockResolvedValue(problem);
		const onresult = vi.fn();
		renderComponent(SystemHealth, { props: { autorun: true, grouped: true, scope: 'system', onresult } });
		await waitFor(() => expect(onresult).toHaveBeenCalledWith(problem));
	});

	it('prints the exact chown fix for a folder ARM cannot write', async () => {
		fetchSystemDiagnostics.mockResolvedValue(problem);
		renderComponent(SystemHealth, { props: { autorun: true, grouped: true, scope: 'system' } });
		expect(await screen.findByText('sudo chown -R 1000:1000 /home/me/arm/media')).toBeInTheDocument();
		expect(screen.getByText('Media library')).toBeInTheDocument();
		expect(screen.getByText('Not writable')).toBeInTheDocument();
		await waitFor(() => expect(screen.getAllByText('751 GB free').length).toBeGreaterThan(0));
	});

	it('explains a down ripper service with its sub-checks, and counts only in-scope problems', async () => {
		fetchSystemDiagnostics.mockResolvedValue(problem);
		renderComponent(SystemHealth, { props: { autorun: true, grouped: true, scope: 'system' } });
		expect(await screen.findByText(/drives can't be enrolled until this is fixed/i)).toBeInTheDocument();
		expect(screen.getByText(/Docker socket: problem/)).toBeInTheDocument();
		expect(screen.getByText('This server')).toBeInTheDocument();
		// MEDIA_ROOT + ripper_manager; the drives warning belongs to a later step
		expect(screen.getByTestId('system-health-summary')).toHaveTextContent('2 problems to fix on the server');
		expect(screen.queryByText('no online drives registered')).toBeNull();
	});

	it('Settings scope lists the other checks too', async () => {
		fetchSystemDiagnostics.mockResolvedValue(problem);
		renderComponent(SystemHealth, { props: { grouped: true } });
		await fireEvent.click(screen.getByTestId('system-health-run'));
		expect(await screen.findByText('no online drives registered')).toBeInTheDocument();
		expect(screen.getByTestId('system-health-summary')).toHaveTextContent('3 problems');
	});

	it('says everything checks out', async () => {
		fetchSystemDiagnostics.mockResolvedValue({ status: 'ok', checks: [{ name: 'config', status: 'ok' }], paths: [] });
		renderComponent(SystemHealth, { props: { autorun: true, grouped: true } });
		expect(await screen.findByText('Everything checks out.')).toBeInTheDocument();
	});
});
