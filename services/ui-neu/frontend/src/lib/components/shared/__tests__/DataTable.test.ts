import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/testing/render';
import DataTableHarness from './DataTableHarness.svelte';

afterEach(cleanup);

const rows = [
	{ id: 'a', name: 'Alpha', count: 3 },
	{ id: 'b', name: 'Beta', count: 0 }
];

describe('DataTable', () => {
	it('is a table named by its label, with one column header per column and one for the actions', () => {
		renderComponent(DataTableHarness, { rows });
		expect(screen.getByRole('table', { name: 'Things' })).toBeInTheDocument();
		const headers = screen.getAllByRole('columnheader');
		expect(headers.map((h) => h.textContent?.trim())).toEqual(['Name', 'Count', 'Actions']);
		for (const h of headers) expect(h).toHaveAttribute('scope', 'col');
	});

	it('draws one body row per item with the action snippet in its last cell', () => {
		renderComponent(DataTableHarness, { rows });
		const body = screen.getAllByRole('row').slice(1);
		expect(body).toHaveLength(2);
		expect(within(body[0]).getByRole('button', { name: 'Open Alpha' })).toBeInTheDocument();
		expect(within(body[1]).getByRole('button', { name: 'Open Beta' })).toBeInTheDocument();
	});

	it('marks only the active row with aria-current', () => {
		renderComponent(DataTableHarness, { rows, activeKey: 'b' });
		const [first, second] = screen.getAllByRole('row').slice(1);
		expect(first).not.toHaveAttribute('aria-current');
		expect(second).toHaveAttribute('aria-current', 'true');
	});

	it('marks no row when nothing is active', () => {
		renderComponent(DataTableHarness, { rows });
		for (const r of screen.getAllByRole('row').slice(1)) expect(r).not.toHaveAttribute('aria-current');
	});

	it('gives end-aligned columns the numeric class, header and cells', () => {
		renderComponent(DataTableHarness, { rows });
		expect(screen.getByRole('columnheader', { name: 'Count' })).toHaveClass('data-table-num');
		expect(screen.getByRole('columnheader', { name: 'Name' })).not.toHaveClass('data-table-num');
		expect(screen.getByRole('cell', { name: '3' })).toHaveClass('data-table-num');
		expect(screen.getByRole('cell', { name: 'Alpha' })).not.toHaveClass('data-table-num');
	});

	it('wraps the table in a box that scrolls sideways', () => {
		renderComponent(DataTableHarness, { rows });
		expect(screen.getByRole('table').parentElement).toHaveClass('data-table-scroll');
	});

	it('shows the empty text, spanning every column, when there are no rows', () => {
		renderComponent(DataTableHarness, { rows: [], empty: 'Nothing here' });
		const cell = screen.getByRole('cell', { name: 'Nothing here' });
		expect(cell).toHaveAttribute('colspan', '3');
	});

	it('shows no body row when there are no rows and no empty text', () => {
		renderComponent(DataTableHarness, { rows: [] });
		expect(screen.getAllByRole('row')).toHaveLength(1);
	});

	it('gives every cell text a title with the full text', () => {
		const long = 'x'.repeat(200);
		renderComponent(DataTableHarness, { rows: [{ id: 'l', name: long, count: 1 }] });
		expect(screen.getByText(long)).toHaveAttribute('title', long);
	});

	it('dims a muted cell and shows its sub line and badges', () => {
		const columns = [
			{
				id: 'name',
				header: 'Name',
				cell: (r: { name: string }) => ({
					text: r.name,
					sub: 'sub line',
					muted: true,
					badges: [
						{ text: 'Warn', tone: 'warn' as const },
						{ text: 'Info', tone: 'info' as const },
						{ text: 'Plain', tone: 'neutral' as const }
					]
				})
			}
		];
		renderComponent(DataTableHarness, { rows, columns });
		const cell = screen.getAllByRole('cell')[0];
		expect(cell).toHaveAttribute('data-muted', 'true');
		expect(within(cell).getByText('sub line')).toHaveAttribute('title', 'sub line');
		expect(within(cell).getByText('Warn')).toHaveClass('badge-warning');
		expect(within(cell).getByText('Info')).toHaveClass('badge-info');
		expect(within(cell).getByText('Plain')).not.toHaveClass('badge-warning', 'badge-info');
	});

	it('leaves a plain cell undimmed with no sub line', () => {
		renderComponent(DataTableHarness, { rows });
		const cell = screen.getByRole('cell', { name: 'Alpha' });
		expect(cell).not.toHaveAttribute('data-muted');
		expect(cell.querySelector('.data-table-sub')).toBeNull();
	});

	it('draws a media pill and the Custom and Built-in tags for pill cells', () => {
		const columns = [
			{
				id: 'm',
				header: 'Media',
				cell: (r: { name: string }) =>
					r.name === 'Alpha'
						? { text: 'Movie', pill: { tone: 'movie' as const } }
						: { text: 'Built-in', pill: { tone: 'builtin' as const } }
			},
			{ id: 't', header: 'Type', cell: () => ({ text: 'Custom', pill: { tone: 'custom' as const } }) }
		];
		renderComponent(DataTableHarness, { rows, columns });
		expect(screen.getByText('Movie')).toHaveAttribute('data-media', 'movie');
		const builtin = screen.getByText('Built-in');
		expect(builtin).toHaveAttribute('data-tone', 'builtin');
		expect(screen.getAllByText('Custom')[0]).toHaveAttribute('data-tone', 'custom');
	});

	it('draws a mono cell in the monospace face and a plain cell without it', () => {
		const columns = [
			{ id: 'p', header: 'Path', cell: () => ({ text: 'a/b.mkv', mono: true }) },
			{ id: 'n', header: 'Name', cell: () => ({ text: 'plain' }) }
		];
		renderComponent(DataTableHarness, { rows, columns });
		expect(screen.getAllByText('a/b.mkv')[0]).toHaveClass('mono');
		expect(screen.getAllByText('plain')[0]).not.toHaveClass('mono');
	});
});
