import type { ComponentProps } from 'svelte';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/testing/render';
import DrivesSettings from '../DrivesSettings.svelte';
import { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';
import { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
import { updateDrive, enrollDrive, rescanDrives } from '$lib/api/drives';
import type { SettingsData } from '$lib/api/settings';
import type { DriveView, SessionView } from '$lib/types/api.gen';

function drive(over: Partial<DriveView> = {}): DriveView {
	return {
		id: 'drv_1',
		hostname: 'arm-ripper-abc',
		device_path: '/dev/sr0',
		display_name: null,
		status: 'online',
		last_seen_at: null,
		media_status: null,
		media_status_at: null,
		default_session_id: null,
		rip_speed: null,
		drive_mode: null,
		uhd_capable: null,
		prescan_cache_mb: null,
		prescan_timeout: null,
		prescan_retries: null,
		disc_enum_timeout: null,
		created_at: null,
		updated_at: null,
		lifecycle: 'enrolled',
		present: true,
		identity_kind: 'by_id',
		serial: 'AAAABBBB000E',
		by_id_name: 'usb-X_AAAABBBB000E-0:0',
		vendor: 'PIONEER',
		model: 'BD-RW BDR-S12JX',
		last_error: null,
		current_job: null,
		...over
	} as DriveView;
}

vi.mock('$lib/api/drives', () => ({
	updateDrive: vi.fn(() => Promise.resolve()),
	unenrollDrive: vi.fn(() => Promise.resolve()),
	enrollDrive: vi.fn(() => Promise.resolve()),
	ignoreDrive: vi.fn(() => Promise.resolve()),
	unignoreDrive: vi.fn(() => Promise.resolve()),
	fetchDriveDiagnostic: vi.fn(() => Promise.resolve({ drives: [], system: [] })),
	rescanDrives: vi.fn(() =>
		Promise.resolve({ online: 0, stale: 0, detected: 0, enrolled: 0, ignored: 0, absent: 0, pruned: 0 })
	)
}));

function settingsData(over: Partial<SettingsData> = {}): SettingsData {
	return {
		config: { auto_rip_on_insert: true },
		arm_config: {},
		...over
	} as unknown as SettingsData;
}

type Props = ComponentProps<typeof DrivesSettings>;

function render(props: Partial<Props> = {}) {
	const onrefresh = vi.fn();
	const options = new DriveSessionOptions();
	const diagnostics = new DriveDiagnostics();
	renderComponent(DrivesSettings, {
		drives: [],
		error: null,
		onrefresh,
		options,
		settings: settingsData(),
		diagnostics,
		...props
	});
	return { onrefresh, options, diagnostics };
}

const mainDrive = () => drive({ display_name: 'Main Drive' });

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DrivesSettings', () => {
	it('shows the error as an alert instead of the drive lists', () => {
		render({
			drives: [
				drive({ id: 'drv_enrolled', display_name: 'Main Drive' }),
				drive({ id: 'drv_detected', lifecycle: 'detected' })
			],
			error: 'Drive service unreachable'
		});
		expect(screen.getByText('Drive service unreachable')).toHaveClass('alert-danger');
		expect(screen.queryByText('Main Drive')).toBeNull();
		expect(screen.queryByTestId('drive-lifecycle-panel')).toBeNull();
	});

	it('still renders the diagnostics panel when there is an error', () => {
		render({ error: 'down' });
		expect(screen.getByRole('button', { name: /Drive Diagnostics/ })).toBeInTheDocument();
	});

	it('renders each enrolled drive as a card in the grid', () => {
		render({
			drives: [drive({ id: 'a', display_name: 'Drive A' }), drive({ id: 'b', display_name: 'Drive B' })]
		});
		expect(screen.getByText('Drive A')).toBeInTheDocument();
		expect(screen.getByText('Drive B')).toBeInTheDocument();
		expect(document.querySelector('.settings-page-drive-grid')).not.toBeNull();
		expect(screen.getAllByTitle('Drive settings')).toHaveLength(2);
	});

	it('shows no card grid when no drive is enrolled', () => {
		const { onrefresh } = render({ drives: [drive({ id: 'drv_detected', lifecycle: 'detected' })] });
		expect(screen.getByTestId('detected-row-drv_detected')).toBeInTheDocument();
		expect(screen.queryByTestId('drive-card-essentials')).toBeNull();
		expect(document.querySelector('.settings-page-drive-grid')).toBeNull();
		expect(onrefresh).not.toHaveBeenCalled();
	});

	it('passes the detected and ignored drives to the lifecycle lists', async () => {
		render({
			drives: [drive({ id: 'drv_detected', lifecycle: 'detected' }), drive({ id: 'drv_ignored', lifecycle: 'ignored' })]
		});
		expect(screen.getByTestId('detected-row-drv_detected')).toBeInTheDocument();
		await fireEvent.click(screen.getByTestId('ignored-toggle'));
		expect(screen.getByTestId('ignored-row-drv_ignored')).toBeInTheDocument();
	});

	it("offers the options' sessions in the card's session picker", () => {
		const options = new DriveSessionOptions();
		options.sessions = [{ id: 's1', name: 'Movie rip', is_builtin: false }] as unknown as SessionView[];
		render({ drives: [mainDrive()], options });
		expect(screen.getByRole('option', { name: 'Movie rip' })).toBeInTheDocument();
	});

	it('shows the Auto global rip mode when auto_rip_on_insert is absent', async () => {
		render({ drives: [mainDrive()], settings: settingsData({ config: {} as never }) });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Auto)');
	});

	it('shows the Auto global rip mode when auto_rip_on_insert is true', async () => {
		render({ drives: [mainDrive()] });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Auto)');
	});

	it('shows the Manual global rip mode when auto_rip_on_insert is false', async () => {
		render({ drives: [mainDrive()], settings: settingsData({ config: { auto_rip_on_insert: false } as never }) });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Manual)');
	});

	it('takes the prescan defaults from arm_config', async () => {
		render({
			drives: [mainDrive()],
			settings: settingsData({
				arm_config: {
					PRESCAN_CACHE_MB: '64',
					PRESCAN_TIMEOUT: '600',
					PRESCAN_RETRIES: '5',
					DISC_ENUM_TIMEOUT: '120'
				}
			})
		});
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Cache/)).toHaveAttribute('placeholder', '64');
		expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '600');
		expect(screen.getByLabelText(/Pre-scan Retries/)).toHaveAttribute('placeholder', '5');
		expect(screen.getByLabelText(/Enum Timeout/)).toHaveAttribute('placeholder', '120');
	});

	it('falls back to the built-in prescan defaults when arm_config has no values', async () => {
		render({ drives: [mainDrive()] });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Cache/)).toHaveAttribute('placeholder', '1');
		expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '300');
		expect(screen.getByLabelText(/Pre-scan Retries/)).toHaveAttribute('placeholder', '3');
		expect(screen.getByLabelText(/Enum Timeout/)).toHaveAttribute('placeholder', '60');
	});

	it('falls back to the built-in defaults when settings carry no config at all', async () => {
		render({ drives: [mainDrive()], settings: undefined as never });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Cache/)).toHaveAttribute('placeholder', '1');
		expect(screen.getByRole('combobox', { name: 'Rip mode' })).toHaveTextContent('Default (Auto)');
	});

	it('calls onrefresh after a rescan', async () => {
		const { onrefresh } = render();
		await fireEvent.click(screen.getByTestId('drive-rescan'));
		await waitFor(() => expect(rescanDrives).toHaveBeenLastCalledWith(false));
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
	});

	it('calls onrefresh after a card update', async () => {
		const { onrefresh } = render({ drives: [mainDrive()] });
		await fireEvent.change(screen.getByRole('combobox', { name: 'Rip mode' }), { target: { value: 'manual' } });
		await waitFor(() => expect(updateDrive).toHaveBeenCalledWith('drv_1', { drive_mode: 'manual' }));
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
	});

	it('calls onrefresh after a lifecycle change', async () => {
		const { onrefresh } = render({ drives: [drive({ id: 'drv_detected', lifecycle: 'detected' })] });
		await fireEvent.click(screen.getByTestId('enroll-drv_detected'));
		await waitFor(() => expect(enrollDrive).toHaveBeenCalledWith('drv_detected'));
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
	});
});
