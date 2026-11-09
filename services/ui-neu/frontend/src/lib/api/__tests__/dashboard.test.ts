import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => {
	const apiFetch = vi.fn((_path: string, _init?: RequestInit) =>
		Promise.resolve({ ripping_paused: false, makemkv_key_valid: true, makemkv_key_checked_at: null })
	);
	// config.ts reads through `get`, which is apiFetch(path, { method: 'GET' }).
	return { apiFetch, get: (path: string) => apiFetch(path, { method: 'GET' }) };
});

vi.mock('$lib/api/drives', () => ({
	fetchDrives: vi.fn()
}));

vi.mock('$lib/api/jobs', () => ({
	fetchJobs: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/transcoder', () => ({
	fetchTranscoderStats: vi.fn(() => Promise.resolve({})),
	fetchTranscoderJobs: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/iso', () => ({
	fetchIsoPreparing: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/notifications', () => ({
	fetchNotificationCount: vi.fn(() => Promise.resolve({ unseen: 0 }))
}));

import { apiFetch } from '$lib/api/client';
import { fetchDrives } from '$lib/api/drives';
import { fetchIsoPreparing } from '$lib/api/iso';
import { fetchJobs } from '$lib/api/jobs';
import { fetchNotificationCount } from '$lib/api/notifications';
import { fetchTranscoderJobs, fetchTranscoderStats } from '$lib/api/transcoder';
import type { DriveView, IsoPrepareView, JobView } from '$lib/types/api.gen';
import { fetchDashboard, fetchDashboardSnapshot, setRippingEnabled } from '../dashboard';

const mockFetchDrives = vi.mocked(fetchDrives);

beforeEach(() => {
	mockFetchDrives.mockClear();
});

describe('fetchDashboard', () => {
	it('counts optical drives only and maps ISO sources', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_1', kind: 'optical', display_name: 'Drive 1' },
			{ id: 'drv_2', kind: 'optical', display_name: 'Drive 2' },
			{ id: 'drv_iso_1', kind: 'virtual', display_name: 'Paddington_2.iso', source_path: 'Paddington_2.iso' }
		] as DriveView[]);

		const dash = await fetchDashboard();

		expect(dash.drives_online).toBe(2);
		expect(dash.iso_sources).toEqual({ drv_iso_1: 'Paddington_2.iso' });
		expect(dash.drive_names).toEqual({ drv_1: 'Drive 1', drv_2: 'Drive 2', drv_iso_1: 'Paddington_2.iso' });
	});

	it('names retired drives but keeps them out of the live counts', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_1', kind: 'optical', lifecycle: 'enrolled', display_name: 'Drive 1' },
			{ id: 'drv_iso_live', kind: 'virtual', lifecycle: 'enrolled', display_name: 'Live.iso' },
			{ id: 'drv_iso_done', kind: 'virtual', lifecycle: 'retired', display_name: 'Done.iso' }
		] as DriveView[]);

		const dash = await fetchDashboard();

		expect(mockFetchDrives).toHaveBeenCalledWith({ includeRetired: true });
		// A finished ISO job still resolves to its file name, not the raw id.
		expect(dash.drive_names.drv_iso_done).toBe('Done.iso');
		expect(dash.iso_sources).toEqual({ drv_iso_live: 'Live.iso' });
		expect(dash.drives_online).toBe(1);
	});

	it('degrades to zero drives when the drives fetch fails', async () => {
		mockFetchDrives.mockRejectedValue(new Error('boom'));

		const dash = await fetchDashboard();

		expect(dash.drives_online).toBe(0);
		expect(dash.iso_sources).toEqual({});
	});

	it('reports the drive fields as null in a snapshot when the drives fetch fails', async () => {
		// null (not {}) is what lets the store hold the last good maps
		mockFetchDrives.mockRejectedValueOnce(new Error('boom'));

		const snap = await fetchDashboardSnapshot();

		expect(snap.drives_online).toBeNull();
		expect(snap.drive_names).toBeNull();
		expect(snap.iso_sources).toBeNull();
		expect(snap.iso_source_kinds).toBeNull();
		expect(snap.drive_source_kinds).toBeNull();
		expect(snap.active_jobs).not.toBeNull();
	});

	it('lists ISO rips that are preparing: live virtual drives with no job yet', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_prep', kind: 'virtual', lifecycle: 'enrolled', display_name: 'MirrorMask.iso' },
			{ id: 'drv_busy', kind: 'virtual', lifecycle: 'enrolled', display_name: 'Busy.iso' },
			{ id: 'drv_done', kind: 'virtual', lifecycle: 'retired', display_name: 'Done.iso' }
		] as DriveView[]);
		vi.mocked(fetchJobs).mockResolvedValueOnce([{ id: 'job_1', drive_id: 'drv_busy', status: 'ripping' }] as JobView[]);
		const at = '2026-10-02T14:00:00Z';
		vi.mocked(fetchIsoPreparing).mockResolvedValueOnce([
			{
				drive_id: 'drv_prep',
				phase: 'extracting',
				progress_pct: 42,
				current_file: 'BDMV/STREAM/1.m2ts',
				updated_at: at
			},
			{ drive_id: 'drv_busy', phase: 'scanning', updated_at: at },
			{ drive_id: 'drv_done', phase: 'scanning', updated_at: at }
		] as IsoPrepareView[]);

		const dash = await fetchDashboard();

		expect(dash.preparing).toEqual([
			{
				drive_id: 'drv_prep',
				phase: 'extracting',
				progress_pct: 42,
				current_file: 'BDMV/STREAM/1.m2ts',
				updated_at: at,
				iso_name: 'MirrorMask.iso',
				iso_kind: 'iso'
			}
		]);
	});

	it('shows no preparing rips when that fetch fails', async () => {
		mockFetchDrives.mockResolvedValue([] as DriveView[]);
		vi.mocked(fetchIsoPreparing).mockRejectedValueOnce(new Error('boom'));

		expect((await fetchDashboard()).preparing).toEqual([]);
	});

	it('records whether each live virtual drive rips an ISO or a disc folder', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_iso', kind: 'virtual', lifecycle: 'enrolled', display_name: 'a.iso', source_kind: 'iso' },
			{ id: 'drv_dir', kind: 'virtual', lifecycle: 'enrolled', display_name: 'Disc 1', source_kind: 'folder' },
			{ id: 'drv_old', kind: 'virtual', lifecycle: 'enrolled', display_name: 'b.iso' }
		] as DriveView[]);
		vi.mocked(fetchIsoPreparing).mockResolvedValueOnce([
			{ drive_id: 'drv_dir', phase: 'scanning', updated_at: '2026-10-02T14:00:00Z' }
		] as IsoPrepareView[]);

		const dash = await fetchDashboard();

		expect(dash.iso_source_kinds).toEqual({ drv_iso: 'iso', drv_dir: 'folder', drv_old: 'iso' });
		expect(dash.preparing[0].iso_kind).toBe('folder');
	});

	it('records the source kind of every virtual drive, retired ones included', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_live', kind: 'virtual', lifecycle: 'enrolled', display_name: 'a.iso', source_kind: 'iso' },
			{ id: 'drv_done', kind: 'virtual', lifecycle: 'retired', display_name: 'Disc 1', source_kind: 'folder' },
			{ id: 'drv_gone', kind: 'virtual', lifecycle: 'retired', display_name: 'b.iso' },
			{ id: 'drv_opt', kind: 'optical', lifecycle: 'enrolled', display_name: 'sr0' }
		] as DriveView[]);

		const dash = await fetchDashboard();

		expect(dash.drive_source_kinds).toEqual({ drv_live: 'iso', drv_done: 'folder', drv_gone: 'iso' });
		expect(dash.iso_source_kinds).toEqual({ drv_live: 'iso' });
	});
});

describe('fetchDashboardSnapshot endpoint failures', () => {
	beforeEach(() => {
		mockFetchDrives.mockReset();
		mockFetchDrives.mockResolvedValue([] as DriveView[]);
	});

	it('reports the config fields as null and db_available false when config fails', async () => {
		vi.mocked(apiFetch).mockRejectedValueOnce(new Error('boom'));

		const snap = await fetchDashboardSnapshot();

		expect(snap.db_available).toBe(false);
		expect(snap.arm_online).toBe(false);
		expect(snap.ripping_enabled).toBeNull();
		expect(snap.makemkv_key_valid).toBeNull();
		expect(snap.makemkv_key_checked_at).toBeNull();
		expect(snap.active_jobs).toEqual([]);
	});

	it('reports arm offline and active_jobs null when the jobs fetch fails', async () => {
		vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('boom'));

		const snap = await fetchDashboardSnapshot();

		expect(snap.arm_online).toBe(false);
		expect(snap.db_available).toBe(true);
		expect(snap.active_jobs).toBeNull();
	});

	it('reports the transcoder offline with no active transcodes when its list fails', async () => {
		vi.mocked(fetchTranscoderJobs).mockRejectedValueOnce(new Error('boom'));

		const snap = await fetchDashboardSnapshot();

		expect(snap.transcoder_online).toBe(false);
		expect(snap.active_transcodes).toEqual([]);
	});

	it('keeps only queued and in-progress transcodes', async () => {
		vi.mocked(fetchTranscoderJobs).mockResolvedValueOnce([
			{ id: 't1', status: 'queued' },
			{ id: 't2', status: 'in_progress' },
			{ id: 't3', status: 'completed' }
		] as never);

		const snap = await fetchDashboardSnapshot();

		expect(snap.transcoder_online).toBe(true);
		expect(snap.active_transcodes.map((t) => t.id)).toEqual(['t1', 't2']);
	});

	it('reports transcoder_stats null when the stats fetch fails and an empty object otherwise', async () => {
		vi.mocked(fetchTranscoderStats).mockRejectedValueOnce(new Error('boom'));
		expect((await fetchDashboardSnapshot()).transcoder_stats).toBeNull();

		expect((await fetchDashboardSnapshot()).transcoder_stats).toEqual({});
	});

	it('reports notification_count null when the count fetch fails', async () => {
		vi.mocked(fetchNotificationCount).mockRejectedValueOnce(new Error('boom'));

		expect((await fetchDashboardSnapshot()).notification_count).toBeNull();
	});

	it('counts zero notifications when the response has no unseen field', async () => {
		vi.mocked(fetchNotificationCount).mockResolvedValueOnce({} as never);

		expect((await fetchDashboardSnapshot()).notification_count).toBe(0);
	});

	it('reports ripping_enabled from the config ripping_paused flag', async () => {
		vi.mocked(apiFetch).mockResolvedValueOnce({ ripping_paused: true });

		expect((await fetchDashboardSnapshot()).ripping_enabled).toBe(false);
	});

	it('drops terminal jobs from active_jobs but keeps ripped ones', async () => {
		vi.mocked(fetchJobs).mockResolvedValueOnce([
			{ id: 'j1', drive_id: 'd', status: 'ripping' },
			{ id: 'j2', drive_id: 'd', status: 'ripped' },
			{ id: 'j3', drive_id: 'd', status: 'failed' },
			{ id: 'j4', drive_id: 'd', status: 'abandoned' }
		] as JobView[]);

		const snap = await fetchDashboardSnapshot();

		expect(snap.active_jobs?.map((j) => j.id)).toEqual(['j1', 'j2']);
	});

	it('names a drive by device_path when it has no display_name', async () => {
		mockFetchDrives.mockResolvedValue([{ id: 'drv_1', kind: 'optical', device_path: '/dev/sr0' }] as DriveView[]);

		expect((await fetchDashboardSnapshot()).drive_names).toEqual({ drv_1: '/dev/sr0' });
	});

	it('labels a virtual drive from the last segment of source_path when display_name is missing', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_v', kind: 'virtual', lifecycle: 'enrolled', device_path: '/dev/v', source_path: '/isos/a/Movie.iso' }
		] as DriveView[]);

		expect((await fetchDashboardSnapshot()).iso_sources).toEqual({ drv_v: 'Movie.iso' });
	});

	it('labels a virtual drive by device_path when display_name and source_path are both missing', async () => {
		mockFetchDrives.mockResolvedValue([
			{ id: 'drv_v', kind: 'virtual', lifecycle: 'enrolled', device_path: '/dev/v' }
		] as DriveView[]);

		expect((await fetchDashboardSnapshot()).iso_sources).toEqual({ drv_v: '/dev/v' });
	});

	it('leaves a preparing row out when its drive has no ISO source', async () => {
		mockFetchDrives.mockResolvedValue([{ id: 'drv_opt', kind: 'optical', display_name: 'sr0' }] as DriveView[]);
		vi.mocked(fetchIsoPreparing).mockResolvedValueOnce([
			{ drive_id: 'drv_opt', phase: 'scanning', updated_at: '2026-10-02T14:00:00Z' }
		] as IsoPrepareView[]);

		expect((await fetchDashboardSnapshot()).preparing).toEqual([]);
	});
});

describe('fetchDashboard defaults for failed reads', () => {
	it('fills every null snapshot field with its empty default', async () => {
		mockFetchDrives.mockRejectedValueOnce(new Error('boom'));
		vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('boom'));
		vi.mocked(fetchNotificationCount).mockRejectedValueOnce(new Error('boom'));
		vi.mocked(apiFetch).mockRejectedValueOnce(new Error('boom'));

		const dash = await fetchDashboard();

		expect(dash.active_jobs).toEqual([]);
		expect(dash.drives_online).toBe(0);
		expect(dash.drive_names).toEqual({});
		expect(dash.iso_sources).toEqual({});
		expect(dash.iso_source_kinds).toEqual({});
		expect(dash.drive_source_kinds).toEqual({});
		expect(dash.notification_count).toBe(0);
		expect(dash.ripping_enabled).toBe(true);
	});
});

describe('setRippingEnabled', () => {
	it.each([
		[true, { ripping_paused: false, hold_for_review: false }],
		[false, { ripping_paused: true, hold_for_review: true }]
	])('patches the config for enabled=%s', async (enabled, body) => {
		await setRippingEnabled(enabled);

		expect(apiFetch).toHaveBeenLastCalledWith('/api/config', { method: 'PATCH', body: JSON.stringify(body) });
	});
});
