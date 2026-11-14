// Pins the notifications page's remaining branches. Dismiss all's empty-list guard is not reached from
// here: the Dismiss All button only shows while a row is unseen. The guard
// lives in NotificationInbox, whose own tests cover it.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import NotificationsPage from '../+page.svelte';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/notifications', () => ({
	fetchNotifications: vi.fn(() =>
		Promise.resolve([
			{
				id: 'n-1',
				event_id: null,
				channel_id: null,
				event_type: 'job.rip_complete',
				title: 'Job Complete',
				message: 'Movie ripped successfully',
				job_id: null,
				seen: false,
				cleared: false,
				seen_at: null,
				cleared_at: null,
				created_at: '2025-06-15T12:00:00Z'
			},
			{
				id: 'n-2',
				event_id: null,
				channel_id: null,
				event_type: 'job.failed',
				title: 'Error',
				message: 'Rip failed',
				job_id: null,
				seen: true,
				cleared: false,
				seen_at: null,
				cleared_at: null,
				created_at: '2025-06-14T10:00:00Z'
			}
		])
	),
	fetchNotificationCount: vi.fn(() => Promise.resolve({ unseen: 1, seen: 1, cleared: 2, total: 4 })),
	dismissNotification: vi.fn(() => Promise.resolve({})),
	dismissAllNotifications: vi.fn(() => Promise.resolve({ updated: 1 })),
	purgeNotifications: vi.fn(() => Promise.resolve({ deleted: 2 }))
}));

import {
	fetchNotifications,
	fetchNotificationCount,
	dismissNotification,
	dismissAllNotifications,
	purgeNotifications
} from '$lib/api/notifications';

function row(overrides: Record<string, unknown>) {
	return {
		id: 'n-x',
		event_id: null,
		channel_id: null,
		event_type: 'job.rip_complete',
		title: 'Row',
		message: 'Row message',
		job_id: null,
		seen: false,
		cleared: false,
		seen_at: null,
		cleared_at: null,
		created_at: '2025-06-15T12:00:00Z',
		...overrides
	};
}

describe('Notifications Page sections', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('load failure', () => {
		it('shows the message of an Error thrown while loading', async () => {
			vi.mocked(fetchNotifications).mockRejectedValueOnce(new Error('inbox down'));
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Failed to load: inbox down')).toBeInTheDocument();
			});
		});

		it('falls back to a generic message when a non-Error is thrown while loading', async () => {
			vi.mocked(fetchNotifications).mockRejectedValueOnce('nope');
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Failed to load: Failed to load notifications')).toBeInTheDocument();
			});
		});
	});

	describe('dismiss', () => {
		it('does not grow the cleared count when the dismissed row is already cleared', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([
				row({ id: 'n-1', title: 'Old one', cleared: true })
			] as never);
			vi.mocked(fetchNotificationCount).mockResolvedValueOnce({ unseen: 1, seen: 0, cleared: 0, total: 1 });
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss'));
			await waitFor(() => {
				expect(screen.queryByText('Dismiss')).not.toBeInTheDocument();
			});
			expect(dismissNotification).toHaveBeenCalledWith('n-1');
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});
	});

	describe('dismiss all', () => {
		it('keeps an already dismissed row dismissed after Dismiss All', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([
				row({ id: 'n-1', title: 'First' }),
				row({ id: 'n-2', title: 'Second' })
			] as never);
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('First')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getAllByText('Dismiss')[0]);
			await waitFor(() => {
				expect(screen.queryByText('First')).not.toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss All'));
			await waitFor(() => {
				expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
			});
			await fireEvent.click(screen.getByRole('checkbox'));
			await waitFor(() => {
				expect(screen.getByText('First')).toBeInTheDocument();
			});
			expect(screen.getByText('First').closest('.notifications-page-card')).toHaveAttribute('data-seen', 'true');
			expect(screen.getByText('Second').closest('.notifications-page-card')).toHaveAttribute('data-seen', 'true');
		});

		it('shows a generic error when dismiss-all fails with a non-Error', async () => {
			vi.mocked(dismissAllNotifications).mockRejectedValueOnce('nope');
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss All'));
			await waitFor(() => {
				expect(screen.getByText('Dismiss all failed')).toBeInTheDocument();
			});
		});
	});

	describe('purge', () => {
		it('shows a generic error when the purge fails with a non-Error', async () => {
			vi.mocked(purgeNotifications).mockRejectedValueOnce('nope');
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Purge Cleared'));
			await fireEvent.click(screen.getByRole('button', { name: 'Purge' }));
			await waitFor(() => {
				expect(screen.getByText('Purge failed')).toBeInTheDocument();
			});
		});

		it('uses the singular wording for one purged notification', async () => {
			vi.mocked(purgeNotifications).mockResolvedValueOnce({ deleted: 1 });
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Purge Cleared'));
			await fireEvent.click(screen.getByRole('button', { name: 'Purge' }));
			await waitFor(() => {
				expect(screen.getByText('Purged 1 cleared notification')).toBeInTheDocument();
			});
		});

		it('closes the dialog and purges nothing when Cancel is clicked', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Purge Cleared'));
			expect(screen.getByRole('button', { name: 'Purge' })).toBeInTheDocument();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			await waitFor(() => {
				expect(screen.queryByRole('button', { name: 'Purge' })).not.toBeInTheDocument();
			});
			expect(purgeNotifications).not.toHaveBeenCalled();
		});
	});

	describe('feedback banner', () => {
		it('removes the banner when its close button is clicked', async () => {
			vi.mocked(purgeNotifications).mockRejectedValueOnce(new Error('API 403: Forbidden'));
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Purge Cleared'));
			await fireEvent.click(screen.getByRole('button', { name: 'Purge' }));
			await waitFor(() => {
				expect(screen.getByText('API 403: Forbidden')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByRole('button', { name: '×' }));
			expect(screen.queryByText('API 403: Forbidden')).not.toBeInTheDocument();
		});
	});

	describe('empty text', () => {
		it('says "No notifications" when Show dismissed is on and the list is empty', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([]);
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('No new notifications')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByRole('checkbox'));
			await waitFor(() => {
				expect(screen.getByText('No notifications')).toBeInTheDocument();
			});
			expect(screen.queryByText('No new notifications')).not.toBeInTheDocument();
		});

		it('says "No new notifications" when only dismissed rows exist and Show dismissed is off', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([row({ id: 'n-1', seen: true, cleared: true })] as never);
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('No new notifications')).toBeInTheDocument();
			});
		});
	});

	describe('sparse rows', () => {
		it('renders a row with no title, message or created_at', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([
				row({ id: 'n-1', title: null, message: null, created_at: null })
			] as never);
			const { container } = renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Notification')).toBeInTheDocument();
			});
			expect(container.querySelector('.notifications-page-row-message')).toBeNull();
			expect(container.querySelector('.notifications-page-row-time')).toBeNull();
		});
	});

	describe('guest', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('sees no Purge, Dismiss All or per-row Dismiss buttons', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
			expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
			expect(screen.queryByText('Dismiss')).not.toBeInTheDocument();
		});
	});
});
