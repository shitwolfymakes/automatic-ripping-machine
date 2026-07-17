import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue({ services: [] })
}));

import { get } from '$lib/api/client';
import { fetchDiagnostics } from '../diagnostics';

const mockGet = vi.mocked(get);

beforeEach(() => {
	mockGet.mockClear();
});

describe('diagnostics api module', () => {
	it('fetchDiagnostics GETs /api/diagnostics', async () => {
		await fetchDiagnostics();
		expect(mockGet).toHaveBeenCalledWith('/api/diagnostics');
	});
});
