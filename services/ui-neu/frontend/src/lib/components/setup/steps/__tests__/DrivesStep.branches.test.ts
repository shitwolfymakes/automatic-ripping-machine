import { describe, it, expect, vi, afterEach } from 'vitest';
import { readable } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type { DriveView, SetupView } from '$lib/types/api.gen';

// Branch pins for DrivesStep, beside steps-behaviour.test.ts. No branch is
// left open.

const diagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({
	fetchSystemVersion: () => Promise.resolve({ version: '3.1.0' }),
	fetchSystemDiagnostics: () => diagnostics()
}));
const fetchDrives = vi.fn();
const updateDrive = vi.fn();
const ignoreDrive = vi.fn();
vi.mock('$lib/api/drives', () => ({
	fetchDrives: () => fetchDrives(),
	rescanDrives: () => Promise.resolve({}),
	enrollDrive: vi.fn(),
	ignoreDrive: (id: string) => ignoreDrive(id),
	unignoreDrive: vi.fn(),
	updateDrive: (id: string, body: unknown) => updateDrive(id, body),
	unenrollDrive: vi.fn(),
	fetchDriveDiagnostic: vi.fn()
}));
const isoLibrary = vi.fn();
vi.mock('$lib/api/iso', () => ({ fetchIsoLibrary: () => isoLibrary() }));
vi.mock('$lib/stores/auth', () => ({ clearPasswordMustChange: vi.fn(), isAdmin: readable(true) }));

import DrivesStep from '../DrivesStep.svelte';

const view = (): SetupView => ({
	completed_at: null,
	progress: {},
	current_step: 'drives',
	admin_default_password: false,
	checklist_dismissed: false
});
type Step = { commit(): Promise<string | false> };

const drive = (over: Partial<DriveView>): DriveView =>
	({
		id: 'drv_a',
		lifecycle: 'enrolled',
		kind: 'optical',
		device_path: '/dev/sr0',
		present: true,
		status: 'online',
		...over
	}) as DriveView;

function setup(drives: DriveView[]) {
	diagnostics.mockResolvedValue({ status: 'ok', checks: [{ name: 'ripper_manager', status: 'ok' }], paths: [] });
	isoLibrary.mockRejectedValue(new Error('503'));
	fetchDrives.mockResolvedValue(drives);
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DrivesStep branches', () => {
	it('draws an enrolled drive as its card and is done when it is online', async () => {
		setup([drive({})]);
		const { component } = renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByTestId('drive-card-essentials')).toBeInTheDocument();
		expect(await (component as unknown as Step).commit()).toBe('done');
	});

	it('reads one drive as "1 drive found" and one image as "1 image"', async () => {
		setup([drive({ id: 'drv_new', lifecycle: 'detected' })]);
		isoLibrary.mockResolvedValue({
			host_path: '/isos',
			subpath: '',
			parent_subpath: null,
			entries: [{ name: 'a.iso', kind: 'iso' }]
		});
		renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByText('1 drive found')).toBeInTheDocument();
		expect(await screen.findByText(/ISO library: on, 1 image$/)).toBeInTheDocument();
	});

	it('adds the ignored count to the drive count', async () => {
		setup([drive({}), drive({ id: 'drv_ign', lifecycle: 'ignored' })]);
		renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByText('1 drive found, 1 ignored')).toBeInTheDocument();
	});

	it('reads several images as plural', async () => {
		setup([]);
		isoLibrary.mockResolvedValue({
			host_path: '/isos',
			subpath: '',
			parent_subpath: null,
			entries: [
				{ name: 'a.iso', kind: 'iso' },
				{ name: 'b.iso', kind: 'iso' }
			]
		});
		renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByText(/ISO library: on, 2 images/)).toBeInTheDocument();
	});

	it('refreshes the drive list after a rescan', async () => {
		setup([]);
		renderComponent(DrivesStep, { props: { view: view() } });
		await screen.findByTestId('drives-empty');
		const before = fetchDrives.mock.calls.length;
		await fireEvent.click(screen.getByTestId('drive-rescan'));
		await waitFor(() => expect(fetchDrives.mock.calls.length).toBeGreaterThan(before));
	});

	it('refreshes the drive list after a lifecycle change', async () => {
		setup([drive({ id: 'drv_new', lifecycle: 'detected' })]);
		ignoreDrive.mockResolvedValue({});
		renderComponent(DrivesStep, { props: { view: view() } });
		const ignore = await screen.findByTestId('ignore-drv_new');
		const before = fetchDrives.mock.calls.length;
		await fireEvent.click(ignore);
		await waitFor(() => expect(fetchDrives.mock.calls.length).toBeGreaterThan(before));
	});

	it('refreshes the drive list after an enrolled drive card saves', async () => {
		setup([drive({})]);
		updateDrive.mockResolvedValue({});
		renderComponent(DrivesStep, { props: { view: view() } });
		const name = await screen.findByLabelText(/friendly name/i);
		const before = fetchDrives.mock.calls.length;
		await fireEvent.input(name, { target: { value: 'Living room' } });
		await fireEvent.blur(name);
		await waitFor(() => expect(fetchDrives.mock.calls.length).toBeGreaterThan(before));
	});

	it('keeps enrolling allowed, with no warning, when the diagnostics fail to load', async () => {
		setup([drive({ id: 'drv_new', lifecycle: 'detected' })]);
		diagnostics.mockRejectedValue(new Error('503'));
		renderComponent(DrivesStep, { props: { view: view() } });
		await screen.findByText(/ISO library: off/);
		expect(screen.queryByTestId('enroll-disabled-reason')).toBeNull();
		expect(screen.getByTestId('enroll-drv_new')).toBeEnabled();
	});
});
