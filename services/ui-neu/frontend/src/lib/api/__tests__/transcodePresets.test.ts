import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([]),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({}),
	del: vi.fn().mockResolvedValue(undefined)
}));

import { get, post, patch, del } from '$lib/api/client';
import {
	fetchTranscodePresets,
	fetchTranscodePreset,
	createTranscodePreset,
	updateTranscodePreset,
	deleteTranscodePreset
} from '../transcodePresets';

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

describe('transcodePresets CRUD api module', () => {
	it('fetchTranscodePresets GETs /api/transcode-presets', async () => {
		await fetchTranscodePresets();
		expect(mockGet).toHaveBeenCalledWith('/api/transcode-presets');
	});

	it('fetchTranscodePresets with a media_type appends the query', async () => {
		await fetchTranscodePresets('tv');
		expect(mockGet).toHaveBeenCalledWith('/api/transcode-presets?media_type=tv');
	});

	it('fetchTranscodePreset GETs /api/transcode-presets/{id}', async () => {
		await fetchTranscodePreset('tpr_1');
		expect(mockGet).toHaveBeenCalledWith('/api/transcode-presets/tpr_1');
	});

	it('createTranscodePreset POSTs /api/transcode-presets with the body', async () => {
		const body = {
			name: 'HQ',
			media_type: 'movie',
			tool: 'handbrake',
			preset_ref: 'Fast 1080p30',
			container: 'mkv',
			codec: 'h265',
			hw_preference: 'any',
			extra_args: null
		} as unknown as Parameters<typeof createTranscodePreset>[0];
		await createTranscodePreset(body);
		expect(mockPost).toHaveBeenCalledWith('/api/transcode-presets', body);
	});

	it('updateTranscodePreset PATCHes /api/transcode-presets/{id} with the body', async () => {
		const body = { name: 'X' } as unknown as Parameters<typeof updateTranscodePreset>[1];
		await updateTranscodePreset('tpr_1', body);
		expect(mockPatch).toHaveBeenCalledWith('/api/transcode-presets/tpr_1', body);
	});

	it('deleteTranscodePreset DELETEs /api/transcode-presets/{id}', async () => {
		await deleteTranscodePreset('tpr_1');
		expect(mockDel).toHaveBeenCalledWith('/api/transcode-presets/tpr_1');
	});
});
