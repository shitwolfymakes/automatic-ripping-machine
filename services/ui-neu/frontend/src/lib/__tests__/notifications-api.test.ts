import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true) {
	return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

import { fetchNotifications, fetchNotificationCount, dismissNotification, dismissAllNotifications } from '../api/notifications';

beforeEach(() => mockFetch.mockReset());

describe('fetchNotifications', () => {
	it('GETs /api/notifications/inbox', async () => {
		mockFetch.mockResolvedValue(jsonResponse([{ id: 'abc', message: 'test' }]));
		const result = await fetchNotifications();
		expect(result).toEqual([{ id: 'abc', message: 'test' }]);
		expect(mockFetch).toHaveBeenCalledWith('/api/notifications/inbox', expect.objectContaining({ method: 'GET' }));
	});
});

describe('fetchNotificationCount', () => {
	it('GETs /api/notifications/inbox/count', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ unseen: 1, seen: 0, cleared: 0, total: 1 }));
		const result = await fetchNotificationCount();
		expect(result.unseen).toBe(1);
		expect(mockFetch).toHaveBeenCalledWith('/api/notifications/inbox/count', expect.objectContaining({ method: 'GET' }));
	});
});

describe('dismissNotification', () => {
	it('PATCHes /api/notifications/inbox/:id with seen+cleared', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'abc', seen: true, cleared: true }));
		await dismissNotification('abc');
		expect(mockFetch).toHaveBeenCalledWith('/api/notifications/inbox/abc', expect.objectContaining({ method: 'PATCH' }));
		const init = mockFetch.mock.calls[0][1] as RequestInit;
		expect(JSON.parse(init.body as string)).toEqual({ seen: true, cleared: true });
	});
});

describe('dismissAllNotifications', () => {
	it('POSTs /api/notifications/inbox/dismiss-all', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await dismissAllNotifications();
		expect(mockFetch).toHaveBeenCalledWith('/api/notifications/inbox/dismiss-all', expect.objectContaining({ method: 'POST' }));
	});
});
