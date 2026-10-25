import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import JobPagination from '../JobPagination.svelte';

describe('JobPagination', () => {
	afterEach(() => cleanup());

	it('shows the summary on a single page and no pager buttons', () => {
		renderComponent(JobPagination, { page: 1, pages: 1, perPage: 48, total: 9, onpage: vi.fn() });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1–9 of 9');
		expect(screen.queryByText('Next')).toBeNull();
	});

	it('shows the summary for an empty list', () => {
		renderComponent(JobPagination, { page: 1, pages: 1, perPage: 48, total: 0, onpage: vi.fn() });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 0–0 of 0');
	});

	it('pages with the buttons when there is more than one page', async () => {
		const onpage = vi.fn();
		renderComponent(JobPagination, { page: 2, pages: 3, perPage: 48, total: 142, onpage });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 49–96 of 142');
		await fireEvent.click(screen.getByText('Next'));
		expect(onpage).toHaveBeenCalledWith(3);
	});
});
