import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([]),
	del: vi.fn().mockResolvedValue(undefined),
	apiFetch: vi.fn().mockResolvedValue({})
}));

import { get, del, apiFetch } from '$lib/api/client';
import { fetchSessionRoutes, upsertSessionRoute, deleteSessionRoute } from '../sessionRoutes';

const mockGet = vi.mocked(get);
const mockDel = vi.mocked(del);
const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
	mockGet.mockClear();
	mockDel.mockClear();
	mockApiFetch.mockClear();
});

describe('sessionRoutes CRUD api module', () => {
	it('fetchSessionRoutes GETs /api/session-routes', async () => {
		await fetchSessionRoutes();
		expect(mockGet).toHaveBeenCalledWith('/api/session-routes');
	});

	it('upsertSessionRoute PUTs /api/session-routes with the body', async () => {
		const body = { media_type: 'music', disc_type: 'cd', session_id: 'ses_music' } as const;
		await upsertSessionRoute(body);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/session-routes', {
			method: 'PUT',
			body: JSON.stringify(body)
		});
	});

	it('deleteSessionRoute DELETEs /api/session-routes/{id}', async () => {
		await deleteSessionRoute('srt_1');
		expect(mockDel).toHaveBeenCalledWith('/api/session-routes/srt_1');
	});
});
