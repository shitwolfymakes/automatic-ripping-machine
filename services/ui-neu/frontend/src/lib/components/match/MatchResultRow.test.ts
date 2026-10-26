import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import MatchResultRow from './MatchResultRow.svelte';

const kolchak = {
	title: 'Kolchak: The Night Stalker',
	year: 1974,
	kind: 'tv',
	provider: 'tmdb',
	poster_url: 'https://image.tmdb.org/k.jpg',
	facts: {
		end_year: 1975,
		rating: 7.9,
		cast: ['Darren McGavin', 'Simon Oakland', 'Jack Grinnage'],
		genres: [],
		creators: []
	}
};

describe('MatchResultRow', () => {
	afterEach(cleanup);

	it('shows title, years and type, two cast names and the rating', () => {
		renderComponent(MatchResultRow, { props: { candidate: kolchak, selected: false, onselect: vi.fn() } });
		expect(screen.getByText('Kolchak: The Night Stalker')).toBeInTheDocument();
		expect(screen.getByText('1974–1975 · TV Series')).toBeInTheDocument();
		expect(screen.getByText('Darren McGavin, Simon Oakland')).toBeInTheDocument();
		expect(screen.getByText('★ 7.9')).toBeInTheDocument();
	});

	it('omits cast and rating when absent', () => {
		renderComponent(MatchResultRow, {
			props: { candidate: { title: 'X', year: 1972, kind: 'movie', facts: null }, selected: false, onselect: vi.fn() }
		});
		expect(screen.getByText('1972 · Movie')).toBeInTheDocument();
		expect(screen.queryByText(/★/)).toBeNull();
	});

	it('reports selection and click', async () => {
		const onselect = vi.fn();
		renderComponent(MatchResultRow, { props: { candidate: kolchak, selected: true, onselect } });
		const row = screen.getByRole('button', { name: /Kolchak/ });
		expect(row).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(row);
		expect(onselect).toHaveBeenCalledOnce();
	});
});
