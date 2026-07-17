import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([]),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({}),
	del: vi.fn().mockResolvedValue(undefined)
}));

import { get, post, patch, del } from '$lib/api/client';
import {
	fetchSessions,
	fetchSession,
	createSession,
	updateSession,
	deleteSession,
	cloneSession,
	previewTemplate
} from '../sessions';

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

describe('sessions CRUD api module', () => {
	it('fetchSessions GETs /api/sessions', async () => {
		await fetchSessions();
		expect(mockGet).toHaveBeenCalledWith('/api/sessions');
	});

	it('fetchSession GETs /api/sessions/{id}', async () => {
		await fetchSession('ses_1');
		expect(mockGet).toHaveBeenCalledWith('/api/sessions/ses_1');
	});

	it('createSession POSTs /api/sessions with the body', async () => {
		const body = {
			name: 'Movies',
			media_type: 'movie',
			rip_preset_id: 'rp_1',
			transcode_preset_id: 'tp_1',
			output_path_template: '/media/{title}'
		} as unknown as Parameters<typeof createSession>[0];
		await createSession(body);
		expect(mockPost).toHaveBeenCalledWith('/api/sessions', body);
	});

	it('updateSession PATCHes /api/sessions/{id} with the body', async () => {
		const body = { name: 'X' } as unknown as Parameters<typeof updateSession>[1];
		await updateSession('ses_1', body);
		expect(mockPatch).toHaveBeenCalledWith('/api/sessions/ses_1', body);
	});

	it('deleteSession DELETEs /api/sessions/{id}', async () => {
		await deleteSession('ses_1');
		expect(mockDel).toHaveBeenCalledWith('/api/sessions/ses_1');
	});

	it('cloneSession POSTs /api/sessions/{id}/clone with the name body', async () => {
		await cloneSession('ses_1', { name: 'Copy' });
		expect(mockPost).toHaveBeenCalledWith('/api/sessions/ses_1/clone', { name: 'Copy' });
	});

	it('previewTemplate POSTs /api/sessions/preview with the body', async () => {
		const body = {
			template: '/media/{title}',
			media_type: 'movie',
			has_transcode_preset: true
		} as unknown as Parameters<typeof previewTemplate>[0];
		await previewTemplate(body);
		expect(mockPost).toHaveBeenCalledWith('/api/sessions/preview', body);
	});
});
