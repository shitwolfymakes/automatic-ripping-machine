import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	del: vi.fn(),
	apiFetch: vi.fn()
}));

import { apiFetch, get, post } from '$lib/api/client';
import { fetchBuiltinPreset, fetchHandbrakeSchema, refreshHandbrakeSchema } from '../handbrake-schema';
import { parseHandbrakeImport } from '../transcode-presets';

beforeEach(() => vi.clearAllMocks());

describe('handbrake schema api', () => {
	it('fetches the slim schema', async () => {
		vi.mocked(get).mockResolvedValue({ handbrake_tag: '1.11.1' });
		expect(await fetchHandbrakeSchema()).toEqual({ handbrake_tag: '1.11.1' });
		expect(get).toHaveBeenCalledWith('/api/handbrake-schema');
	});

	it('url-encodes a built-in preset name', async () => {
		vi.mocked(get).mockResolvedValue({ VideoEncoder: 'x265' });
		await fetchBuiltinPreset('H.265 MKV 1080p30');
		expect(get).toHaveBeenCalledWith('/api/handbrake-schema/builtin/H.265%20MKV%201080p30');
	});

	it('refresh returns the error text, null when absent', async () => {
		vi.mocked(post).mockResolvedValueOnce({ ok: false, error: 'offline' });
		expect(await refreshHandbrakeSchema()).toEqual({ ok: false, error: 'offline' });
		vi.mocked(post).mockResolvedValueOnce({ ok: true });
		expect(await refreshHandbrakeSchema()).toEqual({ ok: true, error: null });
		expect(post).toHaveBeenCalledWith('/api/handbrake-schema/refresh');
	});

	it('posts the raw export text as the body, not JSON-encoded twice', async () => {
		vi.mocked(apiFetch).mockResolvedValue({ presets: [] });
		await parseHandbrakeImport('{"PresetList":[]}');
		expect(apiFetch).toHaveBeenCalledWith('/api/transcode-presets/import/parse', {
			method: 'POST',
			body: '{"PresetList":[]}'
		});
	});
});
