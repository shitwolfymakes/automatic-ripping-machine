import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import TranscodeJobTabs from '../TranscodeJobTabs.svelte';

afterEach(cleanup);

describe('TranscodeJobTabs', () => {
	it('renders the five tabs with their labels in order', () => {
		renderComponent(TranscodeJobTabs, { active: 'all', onselect: vi.fn() });
		const labels = screen.getAllByRole('button').map((b) => b.textContent?.trim());
		expect(labels).toEqual(['All', 'Queued', 'In Progress', 'Done', 'Failed']);
	});

	it('marks only the active tab as selected', () => {
		renderComponent(TranscodeJobTabs, { active: 'done', onselect: vi.fn() });
		const selected = screen.getAllByRole('button').map((b) => b.getAttribute('data-selected'));
		expect(selected).toEqual(['false', 'false', 'false', 'true', 'false']);
	});

	it('calls onselect with the tab key when a tab is clicked', async () => {
		const onselect = vi.fn();
		renderComponent(TranscodeJobTabs, { active: 'all', onselect });
		await fireEvent.click(screen.getByRole('button', { name: 'In Progress' }));
		expect(onselect).toHaveBeenCalledExactlyOnceWith('in_progress');
	});
});
