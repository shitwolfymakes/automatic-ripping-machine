// Every branch of JobPagination's own code is covered. The coverage tool still
// reports three open arms that are Svelte's: `{first}`, `{last}` and `{total}`
// in the summary each compile to `(...) ?? ''`, and all three are numbers.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import JobPagination from '../JobPagination.svelte';

describe('JobPagination', () => {
	afterEach(() => cleanup());

	it('shows the summary on a single page and no pager buttons', () => {
		renderComponent(JobPagination, { page: 1, pages: 1, perPage: 48, total: 9, onpage: vi.fn() });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1-9 of 9');
		expect(screen.queryByText('Next')).toBeNull();
	});

	it('shows the summary for an empty list', () => {
		renderComponent(JobPagination, { page: 1, pages: 1, perPage: 48, total: 0, onpage: vi.fn() });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 0-0 of 0');
	});

	it('pages with the buttons when there is more than one page', async () => {
		const onpage = vi.fn();
		renderComponent(JobPagination, { page: 2, pages: 3, perPage: 48, total: 142, onpage });
		expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 49-96 of 142');
		await fireEvent.click(screen.getByText('Next'));
		expect(onpage).toHaveBeenCalledWith(3);
	});

	it('pages back with Prev and jumps with a page number', async () => {
		const onpage = vi.fn();
		renderComponent(JobPagination, { page: 2, pages: 3, perPage: 48, total: 142, onpage });
		await fireEvent.click(screen.getByText('Prev'));
		expect(onpage).toHaveBeenCalledWith(1);
		await fireEvent.click(screen.getByRole('button', { name: '3' }));
		expect(onpage).toHaveBeenCalledWith(3);
		expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true');
	});

	it('collapses far pages into an ellipsis on each side of the current one', () => {
		renderComponent(JobPagination, { page: 4, pages: 7, perPage: 10, total: 70, onpage: vi.fn() });
		const labels = screen.getAllByRole('button').map((b) => b.textContent?.trim());
		expect(labels).toEqual(['Prev', '1', '3', '4', '5', '7', 'Next']);
		expect(screen.getAllByText('...')).toHaveLength(2);
	});
});
