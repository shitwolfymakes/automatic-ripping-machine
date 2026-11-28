import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn().mockResolvedValue({})
}));

import { apiFetch } from '$lib/api/client';
import { fetchSystemDiagnostics, fetchSystemEnvironment, fetchSystemVersion } from '../system';

const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
	mockApiFetch.mockClear();
});

describe('system api module', () => {
	it('fetchSystemDiagnostics GETs /api/system/diagnostics', async () => {
		await fetchSystemDiagnostics();
		expect(mockApiFetch).toHaveBeenCalledWith('/api/system/diagnostics');
	});

	it('fetchSystemVersion GETs /api/system/version', async () => {
		await fetchSystemVersion();
		expect(mockApiFetch).toHaveBeenCalledWith('/api/system/version');
	});

	it('fetchSystemEnvironment GETs /api/system/environment and returns the body', async () => {
		const body = { version: '3.1.0' };
		mockApiFetch.mockResolvedValueOnce(body);
		await expect(fetchSystemEnvironment()).resolves.toBe(body);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/system/environment');
	});
});
