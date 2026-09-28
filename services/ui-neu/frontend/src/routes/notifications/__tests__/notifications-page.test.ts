import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
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

describe('Notifications Page', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('rendering', () => {
		it('renders page title', () => {
			renderComponent(NotificationsPage);
			expect(screen.getByText('Notifications')).toBeInTheDocument();
		});

		it('shows unseen notification count', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('1 new')).toBeInTheDocument();
			});
		});

		it('renders unseen notifications by default', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
				// Seen notification should be hidden by default
				expect(screen.queryByText('Error')).not.toBeInTheDocument();
			});
		});

		it('shows Dismiss All button for unseen notifications', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			});
		});

		it('shows Show dismissed checkbox', () => {
			renderComponent(NotificationsPage);
			expect(screen.getByText('Show dismissed')).toBeInTheDocument();
		});
	});

	describe('purge cleared', () => {
		it('shows Purge Cleared button when cleared notifications exist', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
		});

		it('does not show Purge Cleared when nothing is cleared, even with seen rows listed', async () => {
			vi.mocked(fetchNotificationCount).mockResolvedValueOnce({ unseen: 1, seen: 1, cleared: 0, total: 2 });
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});

		it('shows Purge Cleared after a single dismiss clears a row', async () => {
			vi.mocked(fetchNotificationCount).mockResolvedValueOnce({ unseen: 1, seen: 1, cleared: 0, total: 2 });
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss')).toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
			await fireEvent.click(screen.getByText('Dismiss'));
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			expect(dismissNotification).toHaveBeenCalledWith('n-1');
		});

		it('purges through the backend and reports the deleted count', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Purge Cleared'));
			await fireEvent.click(screen.getByRole('button', { name: 'Purge' }));
			await waitFor(() => {
				expect(screen.getByText('Purged 2 cleared notifications')).toBeInTheDocument();
			});
			expect(purgeNotifications).toHaveBeenCalledTimes(1);
			// The list and count reload after a purge.
			expect(fetchNotifications).toHaveBeenCalledTimes(2);
			expect(fetchNotificationCount).toHaveBeenCalledTimes(2);
		});

		it('uses the singular for one purged notification', async () => {
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

		it('shows the error when the purge fails', async () => {
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
			expect(fetchNotifications).toHaveBeenCalledTimes(1);
		});

		it('still lists notifications when the count request fails', async () => {
			vi.mocked(fetchNotificationCount).mockRejectedValueOnce(new Error('count down'));
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});
	});

	describe('dismiss all', () => {
		it('makes one dismiss-all call and marks the unseen rows seen', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss All'));
			await waitFor(() => {
				expect(screen.queryByText('1 new')).not.toBeInTheDocument();
			});
			expect(dismissAllNotifications).toHaveBeenCalledTimes(1);
			expect(dismissNotification).not.toHaveBeenCalled();
			expect(screen.queryByText('Job Complete')).not.toBeInTheDocument();
			expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
			// Seen rows are still listed under Show dismissed.
			await fireEvent.click(screen.getByRole('checkbox'));
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
		});

		it('does not make Purge Cleared appear, since dismiss-all does not clear rows', async () => {
			vi.mocked(fetchNotificationCount).mockResolvedValueOnce({ unseen: 1, seen: 1, cleared: 0, total: 2 });
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss All'));
			await waitFor(() => {
				expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});

		it('keeps the rows unseen and shows the error when dismiss-all fails', async () => {
			vi.mocked(dismissAllNotifications).mockRejectedValueOnce(new Error('API 500: Internal Server Error'));
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Dismiss All'));
			await waitFor(() => {
				expect(screen.getByText('API 500: Internal Server Error')).toBeInTheDocument();
			});
			expect(screen.getByText('1 new')).toBeInTheDocument();
			expect(screen.getByText('Job Complete')).toBeInTheDocument();
		});
	});

	describe('empty state', () => {
		it('shows empty state when no notifications', async () => {
			vi.mocked(fetchNotifications).mockResolvedValueOnce([]);
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('No new notifications')).toBeInTheDocument();
			});
		});
	});

	describe('interactions', () => {
		it('shows dismissed notifications when checkbox toggled', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			const checkbox = screen.getByRole('checkbox');
			await fireEvent.click(checkbox);
			await waitFor(() => {
				expect(screen.getByText('Error')).toBeInTheDocument();
			});
		});

		it('renders dismiss button for unseen notifications', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss')).toBeInTheDocument();
			});
		});
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides Dismiss, Dismiss All, and Purge Cleared for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			expect(screen.queryByText('Dismiss')).not.toBeInTheDocument();
			expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});

		it('shows Dismiss, Dismiss All, and Purge Cleared for admins', async () => {
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Dismiss')).toBeInTheDocument();
			});
			expect(screen.getByText('Dismiss All')).toBeInTheDocument();
			expect(screen.getByText('Purge Cleared')).toBeInTheDocument();
		});
	});
});
