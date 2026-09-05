import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SystemHealth from '../SystemHealth.svelte';

const fetchSystemDiagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({ fetchSystemDiagnostics: () => fetchSystemDiagnostics() }));

afterEach(() => { cleanup(); fetchSystemDiagnostics.mockReset(); });

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
