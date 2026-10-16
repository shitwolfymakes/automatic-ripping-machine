import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import MatchDetailPane from './MatchDetailPane.svelte';

const full = {
	title: 'Kolchak: The Night Stalker',
	year: 1974,
	kind: 'tv',
	provider: 'omdb',
	external_ids: { imdb: 'tt0071003' },
	facts: {
		end_year: 1975,
		episode_count: 20,
		rating: 7.9,
		rating_source: 'imdb',
		votes: 9812,
		overview: 'A reporter investigates.',
		genres: ['Horror', 'Mystery'],
		creators: ['Jeff Rice'],
		cast: ['Darren McGavin', 'Simon Oakland']
	}
};
const base = { loading: false, error: null, canUse: true, useLabel: 'Use this match', applying: false };

describe('MatchDetailPane', () => {
	afterEach(cleanup);

	it('shows the full record', () => {
		renderComponent(MatchDetailPane, { props: { ...base, candidate: full, onuse: vi.fn() } });
		expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
		expect(screen.getByText('1974–1975 · TV Series · 20 episodes')).toBeInTheDocument();
		expect(screen.getByText('IMDb')).toBeInTheDocument();
		expect(screen.getByText('★ 7.9')).toBeInTheDocument();
		expect(screen.getByText('9.8K votes')).toBeInTheDocument();
		expect(screen.getByText('tt0071003')).toBeInTheDocument();
		expect(screen.getByText('A reporter investigates.')).toBeInTheDocument();
		expect(screen.getByText('Horror, Mystery')).toBeInTheDocument();
		expect(screen.getByText('Creator')).toBeInTheDocument();
		expect(screen.getByText('Jeff Rice')).toBeInTheDocument();
		expect(screen.getByText('Darren McGavin, Simon Oakland')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Open on IMDb ↗' })).toHaveAttribute(
			'href',
			'https://www.imdb.com/title/tt0071003/'
		);
		expect(screen.queryByTestId('match-pane-skeleton')).toBeNull();
	});

	it('labels a movie director as Director and hides the IMDb link without an id', () => {
		renderComponent(MatchDetailPane, {
			props: {
				...base,
				candidate: { title: 'M', year: 1972, kind: 'movie', facts: { creators: ['D'], genres: [], cast: [] } },
				onuse: vi.fn()
			}
		});
		expect(screen.getByText('Director')).toBeInTheDocument();
		expect(screen.queryByRole('link', { name: 'Open on IMDb ↗' })).toBeNull();
	});

	it('shows a skeleton while loading and the error note on failure', async () => {
		const { rerender } = renderComponent(MatchDetailPane, {
			props: { ...base, loading: true, candidate: { title: 'X', kind: 'tv' }, onuse: vi.fn() }
		});
		expect(screen.getByTestId('match-pane-skeleton')).toBeInTheDocument();
		await rerender({
			...base,
			loading: false,
			error: 'tvdb: miss',
			candidate: { title: 'X', kind: 'tv' },
			onuse: vi.fn()
		});
		expect(screen.queryByTestId('match-pane-skeleton')).toBeNull();
		expect(screen.getByText('tvdb: miss')).toBeInTheDocument();
	});

	it('Use calls onuse; hidden when not allowed; disabled while applying', async () => {
		const onuse = vi.fn();
		const { rerender } = renderComponent(MatchDetailPane, { props: { ...base, candidate: full, onuse } });
		await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
		expect(onuse).toHaveBeenCalledOnce();
		await rerender({ ...base, applying: true, candidate: full, onuse });
		expect(screen.getByRole('button', { name: 'Applying...' })).toBeDisabled();
		await rerender({ ...base, canUse: false, candidate: full, onuse });
		expect(screen.queryByRole('button', { name: 'Use this match' })).toBeNull();
	});
});
