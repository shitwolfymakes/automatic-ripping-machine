import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import TrackSearchResults from '../TrackSearchResults.svelte';
import type { MetadataCandidate } from '$lib/types/api.gen';

function candidate(overrides: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { title: 'Alien', year: 1979, kind: 'movie', poster_url: null, ...overrides };
}

function renderResults(results: MetadataCandidate[]) {
	const onselect = vi.fn();
	const { container } = renderComponent(TrackSearchResults, { props: { results, onselect } });
	return { onselect, container };
}

describe('TrackSearchResults', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('draws one card per result', () => {
		renderResults([candidate({ title: 'A' }), candidate({ title: 'B' })]);
		expect(screen.getAllByRole('button')).toHaveLength(2);
	});

	it('draws at most 8 cards', () => {
		renderResults(Array.from({ length: 10 }, (_, i) => candidate({ title: `Title ${i}` })));
		expect(screen.getAllByRole('button')).toHaveLength(8);
		expect(screen.queryByText('Title 8')).not.toBeInTheDocument();
	});

	it('titles a card with the year in brackets when it has one', () => {
		renderResults([candidate({ title: 'Alien', year: 1979 })]);
		expect(screen.getByRole('button')).toHaveAttribute('title', 'Alien (1979)');
	});

	it('titles a card with the title alone when it has no year', () => {
		renderResults([candidate({ title: 'Alien', year: null })]);
		expect(screen.getByRole('button')).toHaveAttribute('title', 'Alien');
	});

	it('draws the year line, empty when the year is null', () => {
		renderResults([candidate({ title: 'Alien', year: 1979 }), candidate({ title: 'Blade', year: null })]);
		expect(screen.getByText('1979')).toBeInTheDocument();
		const cards = screen.getAllByRole('button');
		expect(cards[1].querySelector('.track-title-search-result-year')).toHaveTextContent('');
	});

	it('draws the poster only when the result has one', () => {
		const { container } = renderResults([
			candidate({ title: 'With', poster_url: 'https://img.test/a.jpg' }),
			candidate({ title: 'Without', poster_url: null })
		]);
		const cards = screen.getAllByRole('button');
		expect(cards[0].querySelector('[data-poster]')).not.toBeNull();
		expect(cards[1].querySelector('[data-poster]')).toBeNull();
		expect(container.querySelectorAll('[data-poster]')).toHaveLength(1);
	});

	it('calls onselect with the clicked result', async () => {
		const first = candidate({ title: 'A' });
		const second = candidate({ title: 'B' });
		const { onselect } = renderResults([first, second]);
		await fireEvent.click(screen.getAllByRole('button')[1]);
		expect(onselect).toHaveBeenCalledTimes(1);
		expect(onselect).toHaveBeenCalledWith(second);
	});
});
