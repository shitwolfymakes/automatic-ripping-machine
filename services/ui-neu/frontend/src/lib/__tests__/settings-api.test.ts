import { describe, it, expect, vi, beforeEach } from 'vitest';

// The settings api uses the Tier A client helpers (get/post/patch). Mock them
// to assert path/method/body without touching fetch.
vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue({}),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({})
}));

import { get, post, patch } from '$lib/api/client';
import {
	fetchSettings,
	saveArmConfig,
	testMetadataKey,
	fetchTranscoderPresets,
	createCustomPreset,
	fetchTranscoderScheme,
	saveTranscoderConfig,
	testTranscoderConnection,
	testTranscoderWebhook,
	fetchSystemInfo
} from '../api/settings';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);
const mockPatch = vi.mocked(patch);

beforeEach(() => {
	mockGet.mockReset().mockResolvedValue({});
	mockPost.mockReset().mockResolvedValue({});
	mockPatch.mockReset().mockResolvedValue({});
});

describe('fetchSettings (v3 fan-out)', () => {
	it('reads config + schema + infra and composes SettingsData', async () => {
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/config') return Promise.resolve({ tmdb_api_key: 'abc', auto_rip_on_insert: true });
			if (path === '/api/settings/schema') return Promise.resolve({ groups: [] });
			if (path === '/api/settings/infra') return Promise.resolve({ db: 'ok' });
			return Promise.resolve({});
		});
		const data = await fetchSettings();
		expect(mockGet).toHaveBeenCalledWith('/api/config');
		expect(mockGet).toHaveBeenCalledWith('/api/settings/schema');
		expect(mockGet).toHaveBeenCalledWith('/api/settings/infra');
		expect(data.config.tmdb_api_key).toBe('abc');
		expect(data.schema.groups).toEqual([]);
		expect(data.infra.db).toBe('ok');
		// arm_config is the config row projected to a loose string map
		expect(data.arm_config.tmdb_api_key).toBe('abc');
		expect(data.arm_config.auto_rip_on_insert).toBe('true');
	});
});

describe('saveArmConfig', () => {
	it('PATCHes /api/config and returns a success envelope', async () => {
		const result = await saveArmConfig({ tmdb_api_key: 'xyz' });
		expect(mockPatch).toHaveBeenCalledWith('/api/config', { tmdb_api_key: 'xyz' });
		expect(result.success).toBe(true);
	});
});

describe('testMetadataKey (v3 GET /api/metadata/test-key)', () => {
	it('GETs test-key with the provider query and adapts the response', async () => {
		mockGet.mockResolvedValue({ provider: 'tmdb', valid: true, detail: 'ok' });
		const result = await testMetadataKey('ignored-inline-key', 'tmdb');
		expect(mockGet).toHaveBeenCalledWith('/api/metadata/test-key?provider=tmdb');
		expect(result).toEqual({ success: true, message: 'ok', provider: 'tmdb' });
	});

	it('maps valid=false to success=false', async () => {
		mockGet.mockResolvedValue({ provider: 'omdb', valid: false, detail: null });
		const result = await testMetadataKey(undefined, 'omdb');
		expect(result.success).toBe(false);
		expect(result.message).toBe('Key is invalid');
	});
});

describe('fetchTranscoderPresets (v3 GET /api/transcode-presets)', () => {
	it('GETs the transcode-presets array', async () => {
		mockGet.mockResolvedValue([{ id: 'p1', name: 'Fast' }]);
		const presets = await fetchTranscoderPresets();
		expect(mockGet).toHaveBeenCalledWith('/api/transcode-presets');
		expect(presets).toHaveLength(1);
		expect(presets[0].name).toBe('Fast');
	});
});

describe('createCustomPreset (v3 POST /api/transcode-presets)', () => {
	it('POSTs the v3 create body', async () => {
		mockPost.mockResolvedValue({ id: 'p2', name: 'Custom' });
		const body = { name: 'Custom', media_type: 'movie' as const, tool: 'handbrake' as const, container: 'mkv' as const };
		const result = await createCustomPreset(body);
		expect(mockPost).toHaveBeenCalledWith('/api/transcode-presets', body);
		expect(result.id).toBe('p2');
	});
});

describe('fetchTranscoderScheme (MISSING in v3)', () => {
	it('resolves null (no transcoder-scheme endpoint) without any fetch', async () => {
		await expect(fetchTranscoderScheme()).resolves.toBeNull();
		expect(mockGet).not.toHaveBeenCalled();
	});
});

describe('MISSING transcoder/system endpoints reject before fetch', () => {
	it('saveTranscoderConfig rejects', async () => {
		await expect(saveTranscoderConfig({})).rejects.toThrow(/not yet available/);
	});
	it('testTranscoderConnection rejects', async () => {
		await expect(testTranscoderConnection()).rejects.toThrow(/not yet available/);
	});
	it('testTranscoderWebhook rejects', async () => {
		await expect(testTranscoderWebhook('s')).rejects.toThrow(/not yet available/);
	});
	it('fetchSystemInfo rejects', async () => {
		await expect(fetchSystemInfo()).rejects.toThrow(/not yet available/);
	});

	it('none of the MISSING stubs hit the client', async () => {
		await Promise.allSettled([
			saveTranscoderConfig({}),
			testTranscoderConnection(),
			testTranscoderWebhook('s'),
			fetchSystemInfo()
		]);
		expect(mockGet).not.toHaveBeenCalled();
		expect(mockPost).not.toHaveBeenCalled();
		expect(mockPatch).not.toHaveBeenCalled();
	});
});
