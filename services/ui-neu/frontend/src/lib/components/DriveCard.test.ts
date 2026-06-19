import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DriveCard from './DriveCard.svelte';
import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve()),
	deleteDrive: vi.fn(() => Promise.resolve())
}));
vi.mock('$lib/api/jobs', () => ({
	triggerManual: vi.fn(() => Promise.resolve({ drive_id: 'drv_1', session_id: null }))
}));
import { triggerManual } from '$lib/api/jobs';
const triggerManualMock = vi.mocked(triggerManual);
import { updateDrive } from '$lib/api/drives';
const updateDriveMock = vi.mocked(updateDrive);

function createDrive(overrides: Partial<Drive> = {}): Drive {
	return {
		id: 'drv_1',
		hostname: 'arm-host',
		device_path: '/dev/sr0',
		display_name: 'Main Drive',
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: false,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		current_job: null,
		...overrides
	};
}

function renderDrive(overrides: Partial<Drive> = {}, sessions: SessionView[] = []) {
	return renderComponent(DriveCard, { props: { drive: createDrive(overrides), sessions } });
}

describe('DriveCard', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('rendering', () => {
		it('renders drive name, device path, 4K toggle, and action bar', () => {
			renderDrive();
			expect(screen.getByText('Main Drive')).toBeInTheDocument();
			expect(screen.getByText('Idle')).toBeInTheDocument();
			const matches = screen.getAllByText('/dev/sr0');
			expect(matches.length).toBeGreaterThan(0);
			// Action bar buttons
			expect(screen.getByTestId('drive-start-rip')).toBeInTheDocument();
			expect(screen.getByTestId('drive-session-select')).toBeInTheDocument();
			expect(screen.queryByText('Remove')).not.toBeInTheDocument();
		});

		it('shows hostname when available', () => {
			renderDrive({ hostname: 'media-box' });
			expect(screen.getByText(/media-box/)).toBeInTheDocument();
		});

		it('shows the 4K toggle', () => {
			renderDrive();
			expect(screen.getByText('4K')).toBeInTheDocument();
		});

		it('shows media status badge when present', () => {
			renderDrive({ media_status: 'loaded' });
			expect(screen.getByText('loaded')).toBeInTheDocument();
		});

		it('falls back to device path when no display name', () => {
			renderDrive({ display_name: null });
			const matches = screen.getAllByText('/dev/sr0');
			expect(matches.find((el) => el.tagName === 'H3')).toBeDefined();
		});

		it('falls back to Drive id when no display name or device path', () => {
			renderDrive({ display_name: null, device_path: '' });
			expect(screen.getByText('Drive drv_1')).toBeInTheDocument();
		});

		it('shows Stale badge and Remove button for offline drives', () => {
			renderDrive({ status: 'offline' });
			expect(screen.getByText('Stale')).toBeInTheDocument();
			expect(screen.getByText('Remove')).toBeInTheDocument();
		});
	});

	describe('prescan overrides badge', () => {
		it('shows custom badge when prescan overrides are set', () => {
			renderDrive({ prescan_cache_mb: 64, prescan_timeout: 600 });
			expect(screen.getByText('2 custom')).toBeInTheDocument();
		});

		it('hides custom badge when no prescan overrides', () => {
			renderDrive();
			expect(screen.queryByText(/custom/)).not.toBeInTheDocument();
		});
	});

	describe('prescan settings panel', () => {
		it('shows prescan inputs in settings panel', async () => {
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByText('Drive Settings')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Cache')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Timeout')).toBeInTheDocument();
			expect(screen.getByText('Pre-scan Retries')).toBeInTheDocument();
			expect(screen.getByText('Enum Timeout')).toBeInTheDocument();
		});

		it('shows tooltips for prescan fields', async () => {
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			expect(screen.getByText(/Community recommends 64-128/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 600/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 3-5/)).toBeInTheDocument();
			expect(screen.getByText(/Community recommends 120/)).toBeInTheDocument();
		});

		it('populates prescan inputs from drive values', async () => {
			renderDrive({ prescan_cache_mb: 128, prescan_retries: 5 });
			await fireEvent.click(screen.getByTitle('Drive settings'));
			const cacheInput = screen.getByLabelText(/Pre-scan Cache/) as HTMLInputElement;
			const retriesInput = screen.getByLabelText(/Pre-scan Retries/) as HTMLInputElement;
			expect(cacheInput.value).toBe('128');
			expect(retriesInput.value).toBe('5');
		});

		it('saves prescan field on blur', async () => {
			const { updateDrive } = await import('$lib/api/drives');
			renderDrive();
			await fireEvent.click(screen.getByTitle('Drive settings'));
			const cacheInput = screen.getByLabelText(/Pre-scan Cache/) as HTMLInputElement;
			await fireEvent.input(cacheInput, { target: { value: '64' } });
			await fireEvent.blur(cacheInput);
			expect(updateDrive).toHaveBeenCalledWith('drv_1', { prescan_cache_mb: 64 });
		});
	});

	describe('interactions', () => {
		it('enters and exits edit mode via Rename button', async () => {
			renderDrive();
			await fireEvent.click(screen.getByText('Rename'));
			expect(screen.getByDisplayValue('Main Drive')).toBeInTheDocument();
			expect(screen.getByText('Save')).toBeInTheDocument();
			await fireEvent.click(screen.getByText('Cancel'));
			expect(screen.getByText('Rename')).toBeInTheDocument();
		});
	});

	describe('manual rip', () => {
		it('renders the session select with "— none —" and prop sessions (built-in flagged)', () => {
			renderDrive({}, [
				{ id: 'ses_1', name: 'Movies', is_builtin: false } as SessionView,
				{ id: 'ses_2', name: 'Stock', is_builtin: true } as SessionView
			]);
			const sel = screen.getByTestId('drive-session-select') as HTMLSelectElement;
			const opts = Array.from(sel.options).map((o) => o.textContent?.trim());
			expect(opts[0]).toBe('- none -');
			expect(opts).toContain('Movies');
			expect(opts).toContain('Stock (built-in)');
		});

		it('Start rip triggers manual with the drive id and null session by default', async () => {
			renderDrive({ id: 'drv_1' });
			await fireEvent.click(screen.getByTestId('drive-start-rip'));
			expect(triggerManualMock).toHaveBeenCalledWith({ drive_id: 'drv_1', session_id: null });
		});

		it('Start rip sends the chosen session id', async () => {
			renderDrive({ id: 'drv_1' }, [{ id: 'ses_1', name: 'Movies', is_builtin: false } as SessionView]);
			await fireEvent.change(screen.getByTestId('drive-session-select'), { target: { value: 'ses_1' } });
			await fireEvent.click(screen.getByTestId('drive-start-rip'));
			expect(triggerManualMock).toHaveBeenCalledWith({ drive_id: 'drv_1', session_id: 'ses_1' });
		});

		it('surfaces a trigger error inline', async () => {
			triggerManualMock.mockRejectedValueOnce(new Error('ripping is paused; no new jobs accepted'));
			renderDrive({ id: 'drv_1' });
			await fireEvent.click(screen.getByTestId('drive-start-rip'));
			await waitFor(() =>
				expect(screen.getByTestId('drive-manual-error')).toHaveTextContent('ripping is paused')
			);
		});

		it('resets the session selection and calls onupdate after a successful rip', async () => {
			const onupdate = vi.fn();
			renderComponent(DriveCard, {
				props: {
					drive: createDrive({ id: 'drv_1' }),
					sessions: [{ id: 'ses_1', name: 'Movies', is_builtin: false } as SessionView],
					onupdate
				}
			});
			const sel = screen.getByTestId('drive-session-select') as HTMLSelectElement;
			await fireEvent.change(sel, { target: { value: 'ses_1' } });
			expect(sel.value).toBe('ses_1');
			await fireEvent.click(screen.getByTestId('drive-start-rip'));
			await waitFor(() => expect(onupdate).toHaveBeenCalledTimes(1));
			expect(sel.value).toBe('');
		});
	});

	describe('default session', () => {
		const sessions = [
			{ id: 'ses_1', name: 'Movies', is_builtin: false } as SessionView,
			{ id: 'ses_2', name: 'Stock', is_builtin: true } as SessionView
		];

		it('seeds the select from drive.default_session_id and lists "— none —" + sessions', async () => {
			renderDrive({ default_session_id: 'ses_1' }, sessions);
			await fireEvent.click(screen.getByTitle('Drive settings'));
			const sel = screen.getByTestId('drive-default-session') as HTMLSelectElement;
			expect(sel.value).toBe('ses_1');
			const opts = Array.from(sel.options).map((o) => o.textContent?.trim());
			expect(opts[0]).toBe('- none -');
			expect(opts).toContain('Movies');
			expect(opts).toContain('Stock (built-in)');
		});

		it('saves the chosen session on change', async () => {
			renderDrive({ id: 'drv_1', default_session_id: null }, sessions);
			await fireEvent.click(screen.getByTitle('Drive settings'));
			await fireEvent.change(screen.getByTestId('drive-default-session'), { target: { value: 'ses_2' } });
			await waitFor(() =>
				expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { default_session_id: 'ses_2' })
			);
		});

		it('clears the default (null) when "— none —" is chosen', async () => {
			renderDrive({ id: 'drv_1', default_session_id: 'ses_1' }, sessions);
			await fireEvent.click(screen.getByTitle('Drive settings'));
			await fireEvent.change(screen.getByTestId('drive-default-session'), { target: { value: '' } });
			await waitFor(() =>
				expect(updateDriveMock).toHaveBeenCalledWith('drv_1', { default_session_id: null })
			);
		});

		it('surfaces a save error inline', async () => {
			updateDriveMock.mockRejectedValueOnce(new Error('default boom'));
			renderDrive({ id: 'drv_1', default_session_id: null }, sessions);
			await fireEvent.click(screen.getByTitle('Drive settings'));
			await fireEvent.change(screen.getByTestId('drive-default-session'), { target: { value: 'ses_1' } });
			await waitFor(() =>
				expect(screen.getByTestId('drive-default-session-error')).toHaveTextContent('default boom')
			);
		});
	});

	describe('skeleton', () => {
		it('renders a SkeletonCard when drive prop is omitted', () => {
			const { container } = renderComponent(DriveCard, { props: {} });
			expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
		});
	});
});
