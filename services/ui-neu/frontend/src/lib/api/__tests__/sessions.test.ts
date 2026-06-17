import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([])
}));

import { get } from '$lib/api/client';
import { fetchSessions } from '../sessions';

const mockGet = vi.mocked(get);

beforeEach(() => {
	mockGet.mockClear();
});

describe('fetchSessions (read-only, EXISTS in v3)', () => {
	it('GETs /api/sessions', async () => {
		await fetchSessions();
		expect(mockGet).toHaveBeenCalledWith('/api/sessions');
	});

	it('returns the SessionView array', async () => {
		const sessions = [{ id: 'ses_1' }, { id: 'ses_2' }];
		mockGet.mockResolvedValueOnce(sessions);
		const result = await fetchSessions();
		expect(result).toBe(sessions);
		expect(result).toHaveLength(2);
	});
});
