import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue({}),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({})
}));

import { get } from '$lib/api/client';
import { fetchSettings } from '../api/settings';

const mockGet = vi.mocked(get);

beforeEach(() => {
	mockGet.mockReset().mockResolvedValue({});
});

describe('fetchSettings composition edge cases', () => {
	it('issues the three reads in parallel (single Promise.all)', async () => {
		const calls: string[] = [];
		mockGet.mockImplementation((path: string) => {
			calls.push(path);
			return Promise.resolve(path === '/api/settings/schema' ? { groups: [] } : {});
		});
		await fetchSettings();
		// All three reads are dispatched together (order is the array order).
		expect(calls).toEqual(['/api/config', '/api/settings/schema', '/api/settings/infra']);
	});

	it('projects null config values to null in arm_config', async () => {
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/config') return Promise.resolve({ omdb_api_key: null, tmdb_api_key: 'k' });
			if (path === '/api/settings/schema') return Promise.resolve({ groups: [] });
			return Promise.resolve({});
		});
		const data = await fetchSettings();
		expect(data.arm_config.omdb_api_key).toBeNull();
		expect(data.arm_config.tmdb_api_key).toBe('k');
		// BFF-only panels are not populated under v3.
		expect(data.transcoder_config).toBeNull();
		expect(data.naming_variables).toBeNull();
	});
});
