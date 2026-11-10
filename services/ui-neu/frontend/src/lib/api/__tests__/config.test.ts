import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn(),
	apiFetch: vi.fn()
}));

import { get } from '$lib/api/client';
import type { ConfigView } from '$lib/types/api.gen';
import { fetchConfig } from '../config';

const mockGet = vi.mocked(get);

const FULL: Partial<ConfigView> = {
	transcode_capable: false,
	transcode_enabled: false,
	search_provider_movie: 'tmdb',
	search_provider_tv: 'tvdb',
	tmdb_api_key: '<hidden>',
	omdb_api_key: '<hidden>',
	tvdb_api_key: '<hidden>'
};

function respondWith(view: Partial<ConfigView>) {
	mockGet.mockResolvedValue(view as ConfigView);
}

beforeEach(() => {
	mockGet.mockReset();
});

describe('fetchConfig', () => {
	it('GETs /api/config and maps every field of the response', async () => {
		respondWith(FULL);
		expect(await fetchConfig()).toEqual({
			transcoder_capable: false,
			transcoder_enabled: false,
			search_provider_movie: 'tmdb',
			search_provider_tv: 'tvdb',
			tmdb_keyed: true,
			omdb_keyed: true,
			tvdb_keyed: true
		});
		expect(mockGet).toHaveBeenCalledWith('/api/config');
	});

	it('reads both transcode flags as true when the response leaves them out', async () => {
		// The backend always sends both flags today.
		const { transcode_capable: _capable, transcode_enabled: _enabled, ...rest } = FULL;
		respondWith(rest);
		const cfg = await fetchConfig();
		expect(cfg.transcoder_capable).toBe(true);
		expect(cfg.transcoder_enabled).toBe(true);
	});

	it('reads the search providers as null when the response leaves them out', async () => {
		const { search_provider_movie: _movie, search_provider_tv: _tv, ...rest } = FULL;
		respondWith(rest);
		const cfg = await fetchConfig();
		expect(cfg.search_provider_movie).toBeNull();
		expect(cfg.search_provider_tv).toBeNull();
	});

	it.each([
		['a real key', 'sk-real'],
		['an empty string', ''],
		['a missing key', undefined]
	])('reads each keyed flag as false for %s', async (_label, key) => {
		respondWith({ ...FULL, tmdb_api_key: key, omdb_api_key: key, tvdb_api_key: key });
		const cfg = await fetchConfig();
		expect(cfg.tmdb_keyed).toBe(false);
		expect(cfg.omdb_keyed).toBe(false);
		expect(cfg.tvdb_keyed).toBe(false);
	});

	it('reads only the mask as a saved key, one provider at a time', async () => {
		respondWith({ ...FULL, omdb_api_key: 'sk-real', tvdb_api_key: '' });
		const cfg = await fetchConfig();
		expect(cfg.tmdb_keyed).toBe(true);
		expect(cfg.omdb_keyed).toBe(false);
		expect(cfg.tvdb_keyed).toBe(false);
	});
});
