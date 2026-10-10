import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import StatusBadge from './StatusBadge.svelte';

describe('StatusBadge', () => {
	afterEach(() => cleanup());

	it.each([
		['ripping', 'Ripping', 'active'],
		['SUCCESS', 'Success', 'success'],
		['copying', 'Copying', 'finishing'],
		// Unmapped statuses humanize (proper-cased) rather than leaking raw text.
		['something_new', 'Something New', 'unknown']
	])('renders status=%s as "%s" with data-status %s', (status, expectedText, expectedDataStatus) => {
		renderComponent(StatusBadge, { props: { status } });
		const badge = screen.getByText(expectedText);
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute('data-status', expectedDataStatus);
	});

	it('renders null status as Unknown', () => {
		renderComponent(StatusBadge, { props: { status: null } });
		const badge = screen.getByText('Unknown');
		expect(badge).toBeInTheDocument();
		expect(badge).toHaveAttribute('data-status', 'unknown');
	});

	it('renders Complete for a done transcode job when given the effective status', () => {
		renderComponent(StatusBadge, { props: { status: 'complete' } });
		expect(screen.getByText('Complete')).toBeInTheDocument();
	});
});
