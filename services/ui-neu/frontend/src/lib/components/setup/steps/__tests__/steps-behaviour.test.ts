import { describe, it, expect, vi, afterEach } from 'vitest';
import { readable } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { SetupView } from '$lib/types/api.gen';

// --- API boundary mocks (the shared components underneath call these) ---
const changePassword = vi.fn((_c: string, _n: string) => Promise.resolve({}));
vi.mock('$lib/api/auth', () => ({ changePassword: (c: string, n: string) => changePassword(c, n) }));
const fetchUsers = vi.fn(() =>
	Promise.resolve([{ id: 'usr_guest', username: 'guest', role: 'guest', disabled: true, last_login_at: null }])
);
const setUserDisabled = vi.fn((_id: string, _d: boolean) => Promise.resolve({}));
vi.mock('$lib/api/users', () => ({
	fetchUsers: () => fetchUsers(),
	setUserDisabled: (id: string, d: boolean) => setUserDisabled(id, d)
}));
vi.mock('$lib/api/resources', () => ({
	fetchResources: () =>
		Promise.resolve({
			cpu_percent: 12,
			cpu_temp: 0,
			memory: { total_gb: 16, used_gb: 4, percent: 25 },
			storage: [{ name: 'MEDIA_ROOT', path: '/media', total_gb: 1000, used_gb: 249, free_gb: 751 }]
		})
}));
const diagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({
	fetchSystemVersion: () => Promise.resolve({ version: '3.1.0' }),
	fetchSystemDiagnostics: () => diagnostics()
}));
const drivesList = vi.fn(() => Promise.resolve([] as unknown[]));
vi.mock('$lib/api/drives', () => ({
	fetchDrives: () => drivesList(),
	rescanDrives: () => Promise.resolve({}),
	enrollDrive: vi.fn(),
	ignoreDrive: vi.fn(),
	unignoreDrive: vi.fn(),
	updateDrive: vi.fn(),
	unenrollDrive: vi.fn(),
	fetchDriveDiagnostic: vi.fn()
}));
const isoLibrary = vi.fn();
vi.mock('$lib/api/iso', () => ({ fetchIsoLibrary: () => isoLibrary() }));
vi.mock('$lib/stores/auth', () => ({ clearPasswordMustChange: vi.fn(), isAdmin: readable(true) }));

import AccountStep from '../AccountStep.svelte';
import SystemStep from '../SystemStep.svelte';
import DrivesStep from '../DrivesStep.svelte';

const view = (over: Partial<SetupView> = {}): SetupView => ({
	completed_at: null,
	progress: {},
	current_step: 'account',
	admin_default_password: true,
	checklist_dismissed: false,
	...over
});
type Step = { commit(): Promise<string | false> };

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('AccountStep', () => {
	it('blocks Continue until the password is valid, then changes it and saves guest access', async () => {
		const setBlocked = vi.fn();
		const { component } = renderComponent(AccountStep, { props: { view: view(), setBlocked } });
		await waitFor(() => expect(setBlocked).toHaveBeenCalledWith(expect.stringMatching(/password/i)));
		expect(await screen.findByText(/751 GB free/)).toBeInTheDocument();
		expect(screen.queryByLabelText(/current password/i)).toBeNull();
		expect(await (component as unknown as Step).commit()).toBe(false);

		await fireEvent.input(screen.getByLabelText(/^new password$/i), { target: { value: 'longenough1' } });
		await fireEvent.input(screen.getByLabelText(/confirm new password/i), { target: { value: 'longenough1' } });
		await waitFor(() => expect(setBlocked).toHaveBeenLastCalledWith(null));
		await fireEvent.click(await screen.findByRole('checkbox', { name: /without signing in/i }));
		expect(await (component as unknown as Step).commit()).toBe('done');
		expect(changePassword).toHaveBeenCalledWith('admin', 'longenough1');
		expect(setUserDisabled).toHaveBeenCalledWith('usr_guest', false);
	});

	it('skips the password when it was already changed', async () => {
		const { component } = renderComponent(AccountStep, { props: { view: view({ admin_default_password: false }) } });
		expect(screen.getByText(/already set/i)).toBeInTheDocument();
		expect(await (component as unknown as Step).commit()).toBe('done');
		expect(changePassword).not.toHaveBeenCalled();
	});
});

describe('SystemStep', () => {
	it('records attention when a storage or service check fails, not for later-step warnings', async () => {
		diagnostics.mockResolvedValue({
			status: 'warning',
			checks: [
				{ name: 'config', status: 'ok' },
				{ name: 'drives', status: 'warning', detail: 'no online drives registered' },
				{ name: 'ripper_manager', status: 'ok', details: [] },
				{ name: 'transcoder', status: 'ok', details: [], location: 'local' }
			],
			paths: []
		});
		const { component } = renderComponent(SystemStep, { props: { view: view() } });
		await screen.findByText('Everything checks out.');
		expect(await (component as unknown as Step).commit()).toBe('done');
		cleanup();
		diagnostics.mockResolvedValue({
			status: 'warning',
			checks: [{ name: 'ripper_manager', status: 'warning', detail: 'docker socket unavailable', details: [] }],
			paths: []
		});
		const second = renderComponent(SystemStep, { props: { view: view() } });
		await screen.findByText(/problem to fix/);
		expect(await (second.component as unknown as Step).commit()).toBe('attention');
	});
});

describe('DrivesStep', () => {
	it('with no drives: troubleshooting, the ISO env line, and attention', async () => {
		diagnostics.mockResolvedValue({ status: 'ok', checks: [{ name: 'ripper_manager', status: 'ok' }], paths: [] });
		isoLibrary.mockRejectedValue(new Error('503'));
		const { component } = renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByTestId('drives-empty')).toHaveTextContent('Plug in the drive and wait 30 seconds.');
		expect(await screen.findByText('ARM_HOST_ISO_LIBRARY_PATH=/path/to/your/isos')).toBeInTheDocument();
		expect(await (component as unknown as Step).commit()).toBe('attention');
	});

	it('an online enrolled drive or an ISO library makes it done; a down ripper service disables Enroll', async () => {
		diagnostics.mockResolvedValue({
			status: 'warning',
			checks: [{ name: 'ripper_manager', status: 'warning' }],
			paths: []
		});
		isoLibrary.mockResolvedValue({
			host_path: '/isos',
			subpath: '',
			parent_subpath: null,
			entries: [{ name: 'a.iso', kind: 'iso' }]
		});
		drivesList.mockResolvedValue([
			{
				id: 'drv_new',
				lifecycle: 'detected',
				kind: 'optical',
				device_path: '/dev/sr1',
				present: true,
				status: 'offline'
			}
		]);
		const { component } = renderComponent(DrivesStep, { props: { view: view() } });
		expect(await screen.findByText(/ISO library: on, 1 image/)).toBeInTheDocument();
		await waitFor(() => expect(screen.getByTestId('enroll-drv_new')).toBeDisabled());
		expect(await (component as unknown as Step).commit()).toBe('done');
	});
});
