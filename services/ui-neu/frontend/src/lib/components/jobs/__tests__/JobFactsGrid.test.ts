import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, within, cleanup } from '$lib/test-utils';
import JobFactsGrid from '../JobFactsGrid.svelte';
import type { MetadataField } from '$lib/jobs/fields';

afterEach(cleanup);

function render(fields: MetadataField[], canEdit = true, onsave = vi.fn().mockResolvedValue(undefined)) {
	renderComponent(JobFactsGrid, { fields, canEdit, onsave });
	return onsave;
}

describe('JobFactsGrid', () => {
	it('renders an empty pad cell with no label', () => {
		const { container } = renderComponent(JobFactsGrid, {
			fields: [{ label: '', value: '', empty: true }],
			canEdit: true,
			onsave: vi.fn()
		});
		const cells = container.querySelectorAll('.job-detail-metadata-cell');
		expect(cells).toHaveLength(1);
		expect(cells[0].querySelector('.job-detail-metadata-label')).toBeNull();
		expect(cells[0].textContent?.trim()).toBe('');
	});

	it('renders a link field as a new-tab link', () => {
		render([{ label: 'IMDb', value: 'tt0078748', link: 'https://imdb.com/title/tt0078748' }]);
		const a = screen.getByRole('link', { name: 'tt0078748' });
		expect(a).toHaveAttribute('href', 'https://imdb.com/title/tt0078748');
		expect(a).toHaveAttribute('target', '_blank');
		expect(a).not.toHaveClass('mono');
	});

	it('renders a mono link field with the mono classes', () => {
		render([{ label: 'IMDb', value: 'tt0078748', link: 'https://imdb.com/x', mono: true }]);
		const a = screen.getByRole('link', { name: 'tt0078748' });
		expect(a).toHaveClass('mono', 'job-detail-metadata-mono');
	});

	it.each(['season', 'disc_number', 'disc_total', 'year'] as const)('edits %s with a number input', async (edit) => {
		render([{ label: 'Field', value: '3', edit, raw: '3' }]);
		const cell = screen.getByTestId(`fact-${edit}`);
		await fireEvent.click(within(cell).getByRole('button'));
		expect(within(cell).getByRole('spinbutton')).toBeInTheDocument();
	});

	it('starts the editor from raw when set', async () => {
		render([{ label: 'Year', value: '1979', edit: 'year', raw: '1979' }]);
		const cell = screen.getByTestId('fact-year');
		await fireEvent.click(within(cell).getByRole('button'));
		expect(within(cell).getByRole('spinbutton')).toHaveValue(1979);
	});

	it('starts the editor empty when raw is unset', async () => {
		render([{ label: 'Year', value: '-', edit: 'year' }]);
		const cell = screen.getByTestId('fact-year');
		await fireEvent.click(within(cell).getByRole('button'));
		expect(within(cell).getByRole('spinbutton')).toHaveValue(null);
	});

	it('offers no editor button when canEdit is off', () => {
		render([{ label: 'Year', value: '1979', edit: 'year', raw: '1979' }], false);
		expect(within(screen.getByTestId('fact-year')).queryByRole('button')).not.toBeInTheDocument();
		expect(screen.getByText('1979')).toBeInTheDocument();
	});

	it('renders a plain field without mono styling or title', () => {
		render([{ label: 'Status', value: 'Done' }]);
		const v = screen.getByText('Done');
		expect(v).not.toHaveClass('mono');
		expect(v).not.toHaveAttribute('title');
	});

	it('renders a mono plain field with the value as its title', () => {
		render([{ label: 'Path', value: '/mnt/x', mono: true }]);
		const v = screen.getByText('/mnt/x');
		expect(v).toHaveClass('mono', 'job-detail-metadata-mono', 'truncate');
		expect(v).toHaveAttribute('title', '/mnt/x');
	});

	it('calls onsave with the field and the raw value when an edit is saved', async () => {
		const onsave = render([{ label: 'Year', value: '1979', edit: 'year', raw: '1979' }]);
		const cell = screen.getByTestId('fact-year');
		await fireEvent.click(within(cell).getByRole('button'));
		const input = within(cell).getByRole('spinbutton');
		await fireEvent.input(input, { target: { value: '1980' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onsave).toHaveBeenCalledWith('year', '1980'));
	});
});
