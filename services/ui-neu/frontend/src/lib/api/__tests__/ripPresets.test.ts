import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([]),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({}),
	del: vi.fn().mockResolvedValue(undefined)
}));

import { get, post, patch, del } from '$lib/api/client';
import {
	fetchRipPresets,
	fetchRipPreset,
	createRipPreset,
	updateRipPreset,
	deleteRipPreset
} from '../ripPresets';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);
const mockPatch = vi.mocked(patch);
const mockDel = vi.mocked(del);

beforeEach(() => {
	mockGet.mockClear();
	mockPost.mockClear();
	mockPatch.mockClear();
	mockDel.mockClear();
});

describe('ripPresets CRUD api module', () => {
	it('fetchRipPresets GETs /api/rip-presets', async () => {
		await fetchRipPresets();
		expect(mockGet).toHaveBeenCalledWith('/api/rip-presets');
	});

	it('fetchRipPreset GETs /api/rip-presets/{id}', async () => {
		await fetchRipPreset('rp_1');
		expect(mockGet).toHaveBeenCalledWith('/api/rip-presets/rp_1');
	});

	it('createRipPreset POSTs /api/rip-presets with the body', async () => {
		const body = {
			name: 'Movies',
			media_type: 'dvd',
			track_selection: 'main_feature',
			identification_mode: 'auto',
			output_mode: 'transcode',
			track_filters_json: { min_duration_seconds: 120 }
		} as unknown as Parameters<typeof createRipPreset>[0];
		await createRipPreset(body);
		expect(mockPost).toHaveBeenCalledWith('/api/rip-presets', body);
	});

	it('updateRipPreset PATCHes /api/rip-presets/{id} with the body', async () => {
		const body = { name: 'X' } as unknown as Parameters<typeof updateRipPreset>[1];
		await updateRipPreset('rp_1', body);
		expect(mockPatch).toHaveBeenCalledWith('/api/rip-presets/rp_1', body);
	});

	it('deleteRipPreset DELETEs /api/rip-presets/{id}', async () => {
		await deleteRipPreset('rp_1');
		expect(mockDel).toHaveBeenCalledWith('/api/rip-presets/rp_1');
	});
});
