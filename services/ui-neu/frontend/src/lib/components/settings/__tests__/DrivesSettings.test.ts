import type { ComponentProps } from 'svelte';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/testing/render';
import DrivesSettings from '../DrivesSettings.svelte';
import { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';
import { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
import { updateDrive, enrollDrive, rescanDrives } from '$lib/api/drives';
import type { SettingsData } from '$lib/api/settings';
import type { DriveView, SessionView, SettingsGroup } from '$lib/types/api.gen';
import { saveArmConfig } from '$lib/api/settings';

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
		rip_end_on_completion_message: null,
		prescan_timeout: null,
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

vi.mock('$lib/api/settings', () => ({
	saveArmConfig: vi.fn(() => Promise.resolve({ success: true }))
}));

function intField(key: string, label: string) {
	return { key, group: 'Drives', tier: 'operator', label, help: '', type: 'int', editable: true, enum_values: null };
}

const drivesGroup = {
	name: 'Drives',
	fields: [
		intField('drive_scan_interval_seconds', 'Drive scan interval (seconds)'),
		intField('drive_detected_prune_days', 'Forget unseen drives after (days)')
	]
} as unknown as SettingsGroup;

function settingsData(over: Partial<SettingsData> = {}): SettingsData {
	return {
		config: { auto_rip_on_insert: true, default_scan_timeout_seconds: 300 },
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
	it('shows the drive scanner tunables as editable fields in a Scanning panel', () => {
		render({
			group: drivesGroup,
			settings: settingsData({ config: { drive_scan_interval_seconds: 30, drive_detected_prune_days: 7 } as never })
		});
		const panel = screen.getByTestId('drive-scanning');
		expect(panel).toHaveTextContent('Scanning');
		expect(screen.getByRole('spinbutton', { name: /Drive scan interval/ })).toHaveValue(30);
		expect(screen.getByRole('spinbutton', { name: /Forget unseen drives/ })).toHaveValue(7);
	});

	it('saves an edited scanner tunable and reports it to onsaved', async () => {
		const onsaved = vi.fn();
		render({
			group: drivesGroup,
			onsaved,
			settings: settingsData({ config: { drive_scan_interval_seconds: 30, drive_detected_prune_days: 7 } as never })
		});
		await fireEvent.input(screen.getByRole('spinbutton', { name: /Drive scan interval/ }), { target: { value: '60' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(saveArmConfig).toHaveBeenCalledWith({ drive_scan_interval_seconds: 60 }));
		expect(onsaved).toHaveBeenCalledWith({ drive_scan_interval_seconds: 60 });
	});

	it('omits the Scanning panel until the schema group is loaded', () => {
		render();
		expect(screen.queryByTestId('drive-scanning')).toBeNull();
	});

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

	it('names the global end-on-completion setting in the drive panel, Off when it is absent', async () => {
		render({ drives: [mainDrive()], settings: settingsData({ config: {} as never }) });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByTestId('drive-end-on-completion').querySelector('option')).toHaveTextContent('Default (Off)');
	});

	it('names an On global end-on-completion setting in the drive panel', async () => {
		render({
			drives: [mainDrive()],
			settings: settingsData({ config: { rip_end_on_completion_message: true } as never })
		});
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByTestId('drive-end-on-completion').querySelector('option')).toHaveTextContent('Default (On)');
	});

	it('offers only the scan timeout, the one prescan setting the ripper reads', async () => {
		render({ drives: [mainDrive()] });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '300');
		expect(screen.queryByLabelText(/Pre-scan Cache/)).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Pre-scan Retries/)).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Enum Timeout/)).not.toBeInTheDocument();
	});

	it("takes the scan timeout placeholder from the backend's published default", async () => {
		render({
			drives: [mainDrive()],
			settings: settingsData({ config: { auto_rip_on_insert: true, default_scan_timeout_seconds: 450 } as never })
		});
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '450');
	});

	it('shows no scan timeout placeholder before the config has loaded', async () => {
		render({ drives: [mainDrive()], settings: undefined as never });
		await fireEvent.click(screen.getByTitle('Drive settings'));
		expect(screen.getByLabelText(/Pre-scan Timeout/)).toHaveAttribute('placeholder', '');
	});

	it('falls back to the built-in defaults when settings carry no config at all', async () => {
		render({ drives: [mainDrive()], settings: undefined as never });
		await fireEvent.click(screen.getByTitle('Drive settings'));
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

	it('renders the Scanning panel with blank fields when settings carry no config', () => {
		render({ group: drivesGroup, settings: undefined as never });
		expect(screen.getByTestId('drive-scanning')).toBeInTheDocument();
		expect(screen.getByRole('spinbutton', { name: /Drive scan interval/ })).toHaveValue(null);
	});
});
