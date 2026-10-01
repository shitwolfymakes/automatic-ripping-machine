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

vi.mock('$lib/api/notifications', () => ({
	fetchNotificationCount: vi.fn(() => Promise.resolve({ unseen: 0 }))
}));

import { fetchDrives } from '$lib/api/drives';
import type { DriveView } from '$lib/types/api.gen';
import { fetchDashboard } from '../dashboard';

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

	it('degrades to zero drives when the drives fetch fails', async () => {
		mockFetchDrives.mockRejectedValue(new Error('boom'));

		const dash = await fetchDashboard();

		expect(dash.drives_online).toBe(0);
		expect(dash.iso_sources).toEqual({});
	});
});
