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
	fetchNotifications: vi.fn(() => Promise.resolve([
		{ id: 'n-1', event_id: null, channel_id: null, event_type: 'job.rip_complete', title: 'Job Complete', message: 'Movie ripped successfully', job_id: null, seen: false, cleared: false, seen_at: null, cleared_at: null, created_at: '2025-06-15T12:00:00Z' },
		{ id: 'n-2', event_id: null, channel_id: null, event_type: 'job.failed', title: 'Error', message: 'Rip failed', job_id: null, seen: true, cleared: true, seen_at: null, cleared_at: null, created_at: '2025-06-14T10:00:00Z' }
	])),
	dismissNotification: vi.fn(() => Promise.resolve({})),
	dismissAllNotifications: vi.fn(() => Promise.resolve())
}));

vi.mock('$lib/api/maintenance', () => ({
	purgeNotifications: vi.fn(() => Promise.resolve({ success: true, count: 0 }))
}));

describe('Notifications Page', () => {
	afterEach(() => cleanup());

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

		it('does not show Purge Cleared button when no cleared notifications', async () => {
			const { fetchNotifications } = await import('$lib/api/notifications');
			vi.mocked(fetchNotifications).mockResolvedValueOnce([
				{ id: 'n-1', event_id: null, channel_id: null, event_type: 'job.rip_complete', title: 'Job Complete', message: 'Movie ripped successfully', job_id: null, seen: false, cleared: false, seen_at: null, cleared_at: null, created_at: '2025-06-15T12:00:00Z' }
			]);
			renderComponent(NotificationsPage);
			await waitFor(() => {
				expect(screen.getByText('Job Complete')).toBeInTheDocument();
			});
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});
	});

	describe('empty state', () => {
		it('shows empty state when no notifications', async () => {
			const { fetchNotifications } = await import('$lib/api/notifications');
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
