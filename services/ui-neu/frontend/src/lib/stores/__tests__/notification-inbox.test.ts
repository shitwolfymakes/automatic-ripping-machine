import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchNotificationsMock = vi.fn();
const fetchNotificationCountMock = vi.fn();
const dismissNotificationMock = vi.fn();
const dismissAllNotificationsMock = vi.fn();
const purgeNotificationsMock = vi.fn();
vi.mock('$lib/api/notifications', () => ({
	fetchNotifications: (...a: unknown[]) => fetchNotificationsMock(...a),
	fetchNotificationCount: (...a: unknown[]) => fetchNotificationCountMock(...a),
	dismissNotification: (...a: unknown[]) => dismissNotificationMock(...a),
	dismissAllNotifications: (...a: unknown[]) => dismissAllNotificationsMock(...a),
	purgeNotifications: (...a: unknown[]) => purgeNotificationsMock(...a)
}));

import { NotificationInbox } from '$lib/stores/notification-inbox.svelte';
import type { NotificationInboxView } from '$lib/types/api.gen';

function row(id: string, seen = false, cleared = false): NotificationInboxView {
	return { id, title: `T${id}`, seen, cleared } as unknown as NotificationInboxView;
}

function deferred<T>() {
	let resolve: (v: T) => void = () => {};
	let reject: (e: unknown) => void = () => {};
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	fetchNotificationsMock.mockReset();
	fetchNotificationCountMock.mockReset();
	dismissNotificationMock.mockReset();
	dismissAllNotificationsMock.mockReset();
	purgeNotificationsMock.mockReset();
});

describe('NotificationInbox', () => {
	it('starts loading, empty, idle and without feedback', () => {
		const inbox = new NotificationInbox();
		expect(inbox.rows).toEqual([]);
		expect(inbox.loading).toBe(true);
		expect(inbox.error).toBeNull();
		expect(inbox.dismissing.size).toBe(0);
		expect(inbox.purging).toBe(false);
		expect(inbox.feedback).toBeNull();
		expect(inbox.clearedCount).toBe(0);
		expect(inbox.unseenCount).toBe(0);
	});

	it('unseenCount follows the rows', () => {
		const inbox = new NotificationInbox();
		inbox.rows = [row('a'), row('b', true), row('c')];
		expect(inbox.unseenCount).toBe(2);
	});

	describe('load', () => {
		it('stores the rows and the cleared count', async () => {
			fetchNotificationsMock.mockResolvedValue([row('a')]);
			fetchNotificationCountMock.mockResolvedValue({ cleared: 4 });
			const inbox = new NotificationInbox();
			await inbox.load();
			expect(inbox.rows).toEqual([row('a')]);
			expect(inbox.clearedCount).toBe(4);
			expect(inbox.loading).toBe(false);
		});

		it('is loading while the request runs', async () => {
			const d = deferred<NotificationInboxView[]>();
			fetchNotificationsMock.mockReturnValue(d.promise);
			fetchNotificationCountMock.mockResolvedValue({ cleared: 0 });
			const inbox = new NotificationInbox();
			inbox.loading = false;
			const pending = inbox.load();
			expect(inbox.loading).toBe(true);
			d.resolve([]);
			await pending;
			expect(inbox.loading).toBe(false);
		});

		it('clears an earlier error when it starts', async () => {
			const d = deferred<NotificationInboxView[]>();
			fetchNotificationsMock.mockReturnValue(d.promise);
			fetchNotificationCountMock.mockResolvedValue({ cleared: 0 });
			const inbox = new NotificationInbox();
			inbox.error = new Error('old');
			const pending = inbox.load();
			expect(inbox.error).toBeNull();
			d.resolve([]);
			await pending;
		});

		it('uses a cleared count of 0 when the count request fails', async () => {
			fetchNotificationsMock.mockResolvedValue([row('a')]);
			fetchNotificationCountMock.mockRejectedValue(new Error('x'));
			const inbox = new NotificationInbox();
			inbox.clearedCount = 5;
			await inbox.load();
			expect(inbox.rows).toEqual([row('a')]);
			expect(inbox.clearedCount).toBe(0);
		});

		it('uses a cleared count of 0 when the count has no cleared', async () => {
			fetchNotificationsMock.mockResolvedValue([]);
			fetchNotificationCountMock.mockResolvedValue({} as never);
			const inbox = new NotificationInbox();
			await inbox.load();
			expect(inbox.clearedCount).toBe(0);
		});

		it('keeps the Error when the rows request fails with an Error', async () => {
			const err = new Error('boom');
			fetchNotificationsMock.mockRejectedValue(err);
			fetchNotificationCountMock.mockResolvedValue({ cleared: 0 });
			const inbox = new NotificationInbox();
			await inbox.load();
			expect(inbox.error).toBe(err);
			expect(inbox.loading).toBe(false);
		});

		it('wraps a non-Error rows failure as Failed to load notifications', async () => {
			fetchNotificationsMock.mockRejectedValue('nope');
			fetchNotificationCountMock.mockResolvedValue({ cleared: 0 });
			const inbox = new NotificationInbox();
			await inbox.load();
			expect(inbox.error).toEqual(new Error('Failed to load notifications'));
		});
	});

	describe('dismiss', () => {
		it('holds the id in dismissing while the request runs and drops it after', async () => {
			const d = deferred<void>();
			dismissNotificationMock.mockReturnValue(d.promise);
			const inbox = new NotificationInbox();
			inbox.rows = [row('a')];
			const pending = inbox.dismiss('a');
			expect(inbox.dismissing.has('a')).toBe(true);
			d.resolve();
			await pending;
			expect(inbox.dismissing.has('a')).toBe(false);
		});

		it('patches the row to seen and cleared and counts it', async () => {
			dismissNotificationMock.mockResolvedValue(undefined);
			const inbox = new NotificationInbox();
			inbox.rows = [row('a'), row('b')];
			inbox.clearedCount = 2;
			await inbox.dismiss('a');
			expect(inbox.rows[0]).toMatchObject({ id: 'a', seen: true, cleared: true });
			expect(inbox.rows[1]).toEqual(row('b'));
			expect(inbox.clearedCount).toBe(3);
		});

		it('adds nothing to the count for a row that was already cleared', async () => {
			dismissNotificationMock.mockResolvedValue(undefined);
			const inbox = new NotificationInbox();
			inbox.rows = [row('a', true, true)];
			inbox.clearedCount = 2;
			await inbox.dismiss('a');
			expect(inbox.clearedCount).toBe(2);
		});

		it('adds nothing to the count for an id not in the rows', async () => {
			dismissNotificationMock.mockResolvedValue(undefined);
			const inbox = new NotificationInbox();
			inbox.rows = [row('a')];
			await inbox.dismiss('zzz');
			expect(inbox.clearedCount).toBe(0);
			expect(inbox.rows).toEqual([row('a')]);
		});

		it('leaves the rows as they were when the request fails', async () => {
			dismissNotificationMock.mockRejectedValue(new Error('x'));
			const inbox = new NotificationInbox();
			const rows = [row('a')];
			inbox.rows = rows;
			await inbox.dismiss('a');
			expect(inbox.rows).toEqual([row('a')]);
			expect(inbox.clearedCount).toBe(0);
			expect(inbox.dismissing.size).toBe(0);
		});
	});

	describe('dismissAll', () => {
		it('makes no request when no row is unseen', async () => {
			const inbox = new NotificationInbox();
			inbox.rows = [row('a', true)];
			await inbox.dismissAll();
			expect(dismissAllNotificationsMock).not.toHaveBeenCalled();
		});

		it('holds every unseen id in dismissing while the request runs', async () => {
			const d = deferred<{ updated: number }>();
			dismissAllNotificationsMock.mockReturnValue(d.promise);
			const inbox = new NotificationInbox();
			inbox.rows = [row('a'), row('b', true), row('c')];
			const pending = inbox.dismissAll();
			expect([...inbox.dismissing].sort()).toEqual(['a', 'c']);
			d.resolve({ updated: 2 });
			await pending;
			expect(inbox.dismissing.size).toBe(0);
		});

		it('adds updated to the count and patches rows that were not cleared', async () => {
			dismissAllNotificationsMock.mockResolvedValue({ updated: 2 });
			const inbox = new NotificationInbox();
			// Cleared but not seen: a patched copy would read seen: true.
			inbox.rows = [row('a'), row('b'), row('c', false, true)];
			inbox.clearedCount = 1;
			await inbox.dismissAll();
			expect(inbox.clearedCount).toBe(3);
			expect(inbox.rows[0]).toMatchObject({ id: 'a', seen: true, cleared: true });
			expect(inbox.rows[1]).toMatchObject({ id: 'b', seen: true, cleared: true });
			expect(inbox.rows[2]).toEqual(row('c', false, true));
		});

		it('reports an Error failure message in feedback', async () => {
			dismissAllNotificationsMock.mockRejectedValue(new Error('nope'));
			const inbox = new NotificationInbox();
			inbox.rows = [row('a')];
			await inbox.dismissAll();
			expect(inbox.feedback).toEqual({ type: 'error', message: 'nope' });
			expect(inbox.dismissing.size).toBe(0);
		});

		it('reports Dismiss all failed for a non-Error failure', async () => {
			dismissAllNotificationsMock.mockRejectedValue('x');
			const inbox = new NotificationInbox();
			inbox.rows = [row('a')];
			await inbox.dismissAll();
			expect(inbox.feedback).toEqual({ type: 'error', message: 'Dismiss all failed' });
		});
	});

	describe('purge', () => {
		beforeEach(() => {
			fetchNotificationsMock.mockResolvedValue([]);
			fetchNotificationCountMock.mockResolvedValue({ cleared: 0 });
		});

		it('is purging while the request runs and not after', async () => {
			const d = deferred<{ deleted: number }>();
			purgeNotificationsMock.mockReturnValue(d.promise);
			const inbox = new NotificationInbox();
			const pending = inbox.purge();
			expect(inbox.purging).toBe(true);
			d.resolve({ deleted: 2 });
			await pending;
			expect(inbox.purging).toBe(false);
		});

		it('reports a plural success and reloads', async () => {
			purgeNotificationsMock.mockResolvedValue({ deleted: 2 });
			const inbox = new NotificationInbox();
			await inbox.purge();
			expect(inbox.feedback).toEqual({ type: 'success', message: 'Purged 2 cleared notifications' });
			expect(fetchNotificationsMock).toHaveBeenCalledTimes(1);
		});

		it('reports a singular success and reloads', async () => {
			purgeNotificationsMock.mockResolvedValue({ deleted: 1 });
			const inbox = new NotificationInbox();
			await inbox.purge();
			expect(inbox.feedback).toEqual({ type: 'success', message: 'Purged 1 cleared notification' });
			expect(fetchNotificationsMock).toHaveBeenCalledTimes(1);
		});

		it('reports an Error failure message', async () => {
			purgeNotificationsMock.mockRejectedValue(new Error('denied'));
			const inbox = new NotificationInbox();
			await inbox.purge();
			expect(inbox.feedback).toEqual({ type: 'error', message: 'denied' });
			expect(inbox.purging).toBe(false);
			expect(fetchNotificationsMock).not.toHaveBeenCalled();
		});

		it('reports Purge failed for a non-Error failure', async () => {
			purgeNotificationsMock.mockRejectedValue('x');
			const inbox = new NotificationInbox();
			await inbox.purge();
			expect(inbox.feedback).toEqual({ type: 'error', message: 'Purge failed' });
		});
	});

	it('clearFeedback empties the feedback', () => {
		const inbox = new NotificationInbox();
		inbox.feedback = { type: 'success', message: 'hi' };
		inbox.clearFeedback();
		expect(inbox.feedback).toBeNull();
	});
});
