import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn(() =>
		Promise.resolve({ ripping_paused: false, makemkv_key_valid: true, makemkv_key_checked_at: null })
	)
}));

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

import { fetchDrives } from '$lib/api/drives';
import { fetchIsoPreparing } from '$lib/api/iso';
import { fetchJobs } from '$lib/api/jobs';
import type { DriveView, IsoPrepareView, JobView } from '$lib/types/api.gen';
import { fetchDashboard, fetchDashboardSnapshot } from '../dashboard';

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
