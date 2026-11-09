import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import type { NotificationInboxView } from '$lib/types/api.gen';
import NotificationCard from '../NotificationCard.svelte';

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

import * as auth from '$lib/stores/auth';
import { formatDateTime } from '$lib/utils/format';

const setRole = (auth as unknown as { __setRole: (r: string | null) => void }).__setRole;

function row(overrides: Partial<NotificationInboxView> = {}): NotificationInboxView {
	return {
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
		created_at: '2025-06-15T12:00:00Z',
		...overrides
	} as NotificationInboxView;
}

function renderCard(notif: NotificationInboxView, dismissing = false, ondismiss = vi.fn()) {
	const result = renderComponent(NotificationCard, { notif, dismissing, ondismiss });
	return { ...result, ondismiss };
}

describe('NotificationCard', () => {
	beforeEach(() => {
		vi.useFakeTimers({ toFake: ['Date'] });
		vi.setSystemTime(new Date('2025-06-15T13:00:00Z'));
		setRole('admin');
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('marks an unseen row with the dot and data-seen false', () => {
		const { container } = renderCard(row());
		expect(container.querySelector('.notifications-page-card')).toHaveAttribute('data-seen', 'false');
		expect(container.querySelector('.notifications-page-row-dot')).toBeInTheDocument();
	});

	it('marks a seen row with no dot and data-seen true', () => {
		const { container } = renderCard(row({ seen: true }));
		expect(container.querySelector('.notifications-page-card')).toHaveAttribute('data-seen', 'true');
		expect(container.querySelector('.notifications-page-row-dot')).toBeNull();
	});

	it('shows the title', () => {
		renderCard(row());
		expect(screen.getByText('Job Complete')).toBeInTheDocument();
	});

	it('falls back to Notification when there is no title', () => {
		renderCard(row({ title: undefined }));
		expect(screen.getByText('Notification')).toBeInTheDocument();
	});

	it('shows the message', () => {
		renderCard(row());
		expect(screen.getByText('Movie ripped successfully')).toBeInTheDocument();
	});

	it('omits the message when there is none', () => {
		const { container } = renderCard(row({ message: undefined }));
		expect(container.querySelector('.notifications-page-row-message')).toBeNull();
	});

	it('shows the relative time with the absolute date as its title', () => {
		const { container } = renderCard(row());
		const time = container.querySelector('.notifications-page-row-time');
		expect(time).toHaveTextContent('1h ago');
		expect(time).toHaveAttribute('title', formatDateTime('2025-06-15T12:00:00Z'));
	});

	it('omits the time when there is no created_at', () => {
		const { container } = renderCard(row({ created_at: null }));
		expect(container.querySelector('.notifications-page-row-time')).toBeNull();
	});

	it('lets an admin dismiss an unseen row, passing its id', async () => {
		const { ondismiss } = renderCard(row());
		await fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
		expect(ondismiss).toHaveBeenCalledWith('n-1');
	});

	it('shows a disabled ... button while dismissing', () => {
		renderCard(row(), true);
		const button = screen.getByRole('button', { name: '...' });
		expect(button).toBeDisabled();
	});

	it('has no Dismiss button on a seen row', () => {
		renderCard(row({ seen: true }));
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('has no Dismiss button for a guest', () => {
		setRole(null);
		renderCard(row());
		expect(screen.queryByRole('button')).toBeNull();
	});
});
