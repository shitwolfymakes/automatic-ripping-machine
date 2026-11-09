import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import InboxEmptyState from '../InboxEmptyState.svelte';

afterEach(cleanup);

describe('InboxEmptyState', () => {
	it('says there are no new notifications when dismissed ones are hidden', () => {
		renderComponent(InboxEmptyState, { props: { showCleared: false } });
		expect(screen.getByText('No new notifications')).toBeInTheDocument();
	});

	it('says there are no notifications when dismissed ones are shown', () => {
		renderComponent(InboxEmptyState, { props: { showCleared: true } });
		expect(screen.getByText('No notifications')).toBeInTheDocument();
		expect(screen.queryByText('No new notifications')).not.toBeInTheDocument();
	});

	it('shows the bell icon', () => {
		const { container } = renderComponent(InboxEmptyState, { props: { showCleared: false } });
		expect(container.querySelector('svg.notifications-page-empty-icon')).not.toBeNull();
	});
});
