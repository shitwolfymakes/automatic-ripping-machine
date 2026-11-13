import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, within, cleanup } from '$lib/test-utils';
import { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
import { fetchDriveDiagnostic } from '$lib/api/drives';
import type { DriveDiagnosticItem, DriveDiagnosticResponse } from '$lib/types/api.gen';
import DriveDiagnosticsPanel from '../DriveDiagnosticsPanel.svelte';

vi.mock('$lib/api/drives', () => ({
	fetchDriveDiagnostic: vi.fn()
}));

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

function drive(overrides: Partial<DriveDiagnosticItem> = {}): DriveDiagnosticItem {
	return {
		id: 'd1',
		lifecycle: 'active',
		present: true,
		identity_kind: null,
		device_path: '/dev/sr0',
		status: null,
		media_status: null,
		media_status_at: null,
		container: null,
		last_error: null,
		healthy: true,
		notes: [],
		...overrides
	} as unknown as DriveDiagnosticItem;
}

function result(drives: DriveDiagnosticItem[], system?: string[]): DriveDiagnosticResponse {
	return { drives, system } as DriveDiagnosticResponse;
}

function render(setup: (d: DriveDiagnostics) => void = () => {}) {
	const diagnostics = new DriveDiagnostics();
	diagnostics.open = true;
	setup(diagnostics);
	renderComponent(DriveDiagnosticsPanel, { diagnostics });
	return diagnostics;
}

const runButton = () => screen.getByRole('button', { name: /Run Check|Running\.\.\./ }) as HTMLButtonElement;

describe('DriveDiagnosticsPanel', () => {
	it('shows only the disclosure button while closed', () => {
		render((d) => (d.open = false));
		const toggle = screen.getByRole('button', { name: /Drive Diagnostics/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByRole('button', { name: 'Run Check' })).not.toBeInTheDocument();
	});

	it('shows the panel while open', () => {
		render();
		expect(screen.getByRole('button', { name: /Drive Diagnostics/ })).toHaveAttribute('aria-expanded', 'true');
		expect(runButton()).toBeInTheDocument();
	});

	it('toggles open and aria-expanded when the disclosure button is clicked', async () => {
		const d = render((x) => (x.open = false));
		const toggle = screen.getByRole('button', { name: /Drive Diagnostics/ });
		await fireEvent.click(toggle);
		expect(d.open).toBe(true);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		await fireEvent.click(toggle);
		expect(d.open).toBe(false);
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
	});

	it('shows Run Check, enabled and not busy, while idle', () => {
		render();
		expect(runButton()).toHaveTextContent('Run Check');
		expect(runButton()).not.toBeDisabled();
		expect(runButton()).toHaveAttribute('data-busy', 'false');
	});

	it('shows Running..., disabled and busy, while running', () => {
		render((d) => (d.running = true));
		expect(runButton()).toHaveTextContent('Running...');
		expect(runButton()).toBeDisabled();
		expect(runButton()).toHaveAttribute('data-busy', 'true');
	});

	it('fetches the diagnostic when Run Check is clicked', async () => {
		vi.mocked(fetchDriveDiagnostic).mockResolvedValue(result([drive()]));
		const d = render();
		await fireEvent.click(runButton());
		await waitFor(() => expect(d.result).not.toBeNull());
		expect(fetchDriveDiagnostic).toHaveBeenCalledTimes(1);
		expect(await screen.findByTestId('diag-drive-d1')).toBeInTheDocument();
	});

	it('shows the last run time when there is one', () => {
		render((d) => (d.lastRun = '10:30:00'));
		expect(screen.getByText('Last run: 10:30:00')).toBeInTheDocument();
	});

	it('omits the last run time when there is none', () => {
		render();
		expect(screen.queryByText(/Last run:/)).not.toBeInTheDocument();
	});

	it('shows the error when there is one', () => {
		render((d) => (d.error = 'Diagnostic failed'));
		expect(screen.getByText('Diagnostic failed')).toBeInTheDocument();
	});

	it('omits the error when there is none', () => {
		render();
		expect(screen.queryByText('Diagnostic failed')).not.toBeInTheDocument();
	});

	it('shows the Run Check hint while idle with no result', () => {
		render();
		expect(screen.getByText(/Click "Run Check" to scan drives/)).toBeInTheDocument();
	});

	it('shows no hint while running with no result', () => {
		render((d) => (d.running = true));
		expect(screen.queryByText(/Click "Run Check" to scan drives/)).not.toBeInTheDocument();
	});

	it('shows the system notes when the result has them', () => {
		render((d) => (d.result = result([drive()], ['udev missing', 'no rules'])));
		const box = screen.getByTestId('diag-system');
		expect(within(box).getByText('udev missing')).toBeInTheDocument();
		expect(within(box).getByText('no rules')).toBeInTheDocument();
	});

	it('omits the system notes when the result has none', () => {
		render((d) => (d.result = result([drive()])));
		expect(screen.queryByTestId('diag-system')).not.toBeInTheDocument();
	});

	it('omits the system notes when the system list is empty', () => {
		render((d) => (d.result = result([drive()], [])));
		expect(screen.queryByTestId('diag-system')).not.toBeInTheDocument();
	});

	it('shows All OK in a success bar when every drive is healthy and there are no system notes', () => {
		render((d) => (d.result = result([drive()])));
		const title = screen.getByText('All OK');
		expect(title.closest('.alert')).toHaveClass('alert-success');
	});

	it('shows Issues Found in a warning bar when a drive is unhealthy', () => {
		render((d) => (d.result = result([drive({ healthy: false })])));
		const title = screen.getByText('Issues Found');
		expect(title.closest('.alert')).toHaveClass('alert-warning');
	});

	it('shows Issues Found in a warning bar from system notes alone', () => {
		render((d) => (d.result = result([drive()], ['udev missing'])));
		const title = screen.getByText('Issues Found');
		expect(title.closest('.alert')).toHaveClass('alert-warning');
	});

	it('writes the drive count in the singular for one drive', () => {
		render((d) => (d.result = result([drive()])));
		expect(screen.getByText(/^\s*1 drive\s*$/)).toBeInTheDocument();
	});

	it('writes the drive count in the plural for several drives', () => {
		render((d) => (d.result = result([drive(), drive({ id: 'd2' })])));
		expect(screen.getByText(/^\s*2 drives\s*$/)).toBeInTheDocument();
	});

	it('shows a present drive as connected, not warned', () => {
		render((d) => (d.result = result([drive()])));
		const row = screen.getByTestId('diag-drive-d1');
		expect(within(row).getByText('/dev/sr0')).toBeInTheDocument();
		expect(within(row).getByText('active')).toBeInTheDocument();
		expect(within(row).getByText('connected')).toHaveAttribute('data-warn', 'false');
	});

	it('shows an absent drive as not connected and warned', () => {
		render((d) => (d.result = result([drive({ present: false })])));
		expect(screen.getByText('not connected')).toHaveAttribute('data-warn', 'true');
	});

	it('shows the container, ripper status, media status and heartbeat when present', () => {
		render(
			(d) =>
				(d.result = result([
					drive({
						container: 'ripper-1',
						status: 'idle' as never,
						media_status: 'no_media' as never,
						media_status_at: '2026-01-02T03:04:05Z'
					})
				]))
		);
		expect(screen.getByText('container: ripper-1')).toBeInTheDocument();
		expect(screen.getByText('ripper: idle')).toBeInTheDocument();
		expect(screen.getByText('media: no media')).toBeInTheDocument();
		expect(screen.getByText(/^heartbeat /)).toBeInTheDocument();
	});

	it('omits the container, ripper status, media status and heartbeat when absent', () => {
		render((d) => (d.result = result([drive()])));
		expect(screen.queryByText(/container:/)).not.toBeInTheDocument();
		expect(screen.queryByText(/ripper:/)).not.toBeInTheDocument();
		expect(screen.queryByText(/media:/)).not.toBeInTheDocument();
		expect(screen.queryByText(/heartbeat/)).not.toBeInTheDocument();
	});

	it('shows OK for a healthy drive', () => {
		render((d) => (d.result = result([drive()])));
		expect(within(screen.getByTestId('diag-drive-d1')).getByText('OK')).toBeInTheDocument();
	});

	it('omits OK and flags a drive that is unhealthy', () => {
		render((d) => (d.result = result([drive({ healthy: false })])));
		const row = screen.getByTestId('diag-drive-d1');
		expect(within(row).queryByText('OK')).not.toBeInTheDocument();
		expect(row).toHaveAttribute('data-flagged', 'true');
	});

	it('shows the last error when the drive has one', () => {
		render((d) => (d.result = result([drive({ last_error: 'SCSI NOT_READY' })])));
		expect(screen.getByText('SCSI NOT_READY')).toHaveClass('field-error');
	});

	it('omits the last error when the drive has none', () => {
		render((d) => (d.result = result([drive()])));
		expect(document.querySelector('.field-error')).toBeNull();
	});

	it('shows an ignored note as ignored', () => {
		render((d) => (d.result = result([drive({ healthy: false, notes: ['ignored'] })])));
		const row = screen.getByTestId('diag-drive-d1');
		expect(within(row).getByText('ignored')).toHaveClass('settings-page-diag-ignored');
		expect(row.querySelector('.settings-page-diag-warn-icon')).toBeNull();
	});

	it("shows a healthy drive's note as informational", () => {
		render((d) => (d.result = result([drive({ notes: ['firmware old'] })])));
		const row = screen.getByTestId('diag-drive-d1');
		expect(within(row).getByText('firmware old')).toHaveClass('settings-page-diag-ignored');
		expect(row.querySelector('.settings-page-diag-warn-icon')).toBeNull();
	});

	it("shows an unhealthy drive's note with the warning glyph", () => {
		render((d) => (d.result = result([drive({ healthy: false, notes: ['no udev rule'] })])));
		const row = screen.getByTestId('diag-drive-d1');
		expect(within(row).getByText('no udev rule')).toHaveClass('settings-page-diag-warn-text');
		expect(row.querySelector('.settings-page-diag-warn-icon')).not.toBeNull();
		expect(within(row).queryByText('unhealthy')).not.toBeInTheDocument();
	});

	it('shows unhealthy for an unhealthy drive with no notes', () => {
		render((d) => (d.result = result([drive({ healthy: false })])));
		expect(within(screen.getByTestId('diag-drive-d1')).getByText('unhealthy')).toBeInTheDocument();
	});

	it('omits unhealthy for a healthy drive with no notes', () => {
		render((d) => (d.result = result([drive()])));
		expect(screen.queryByText('unhealthy')).not.toBeInTheDocument();
	});
});
