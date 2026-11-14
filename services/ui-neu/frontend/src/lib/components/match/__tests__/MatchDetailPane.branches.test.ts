import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import MatchDetailPane from '../MatchDetailPane.svelte';

// Branch pins for MatchDetailPane's rating line, beside MatchDetailPane.test.ts.
// No branch is left open.

const base = { loading: false, error: null, canUse: true, useLabel: 'Use this match', applying: false, onuse: vi.fn() };
const withFacts = (facts: Record<string, unknown>, external_ids: Record<string, string> | null = null) => ({
	...base,
	candidate: { title: 'X', kind: 'tv', external_ids, facts }
});

describe('MatchDetailPane rating line', () => {
	afterEach(cleanup);

	it('gives an IMDb rating the IMDb badge class and label', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: 7.9, rating_source: 'imdb' }) });
		const badge = screen.getByText('IMDb');
		expect(badge).toHaveClass('badge', 'badge-imdb');
	});

	it('labels another known source without the IMDb class', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: 8.1, rating_source: 'tmdb' }) });
		const badge = screen.getByText('TMDb');
		expect(badge).toHaveClass('badge');
		expect(badge).not.toHaveClass('badge-imdb');
		expect(screen.getByText('★ 8.1')).toBeInTheDocument();
	});

	it('labels an unknown source "Rating"', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: 6, rating_source: 'rottentomatoes' }) });
		const badge = screen.getByText('Rating');
		expect(badge).not.toHaveClass('badge-imdb');
		expect(screen.getByText('★ 6.0')).toBeInTheDocument();
	});

	it('labels a missing source "Rating"', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: 5.5 }) });
		expect(screen.getByText('Rating')).toBeInTheDocument();
		expect(screen.getByText('★ 5.5')).toBeInTheDocument();
	});

	it('shows no votes when there are none', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: 7.9, rating_source: 'imdb', votes: 0 }) });
		expect(screen.getByText('★ 7.9')).toBeInTheDocument();
		expect(screen.queryByText(/votes/)).toBeNull();
	});

	it('still shows the IMDb id when there is no rating', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: null }, { imdb: 'tt0071003' }) });
		expect(screen.getByText('tt0071003')).toBeInTheDocument();
		expect(screen.queryByText('IMDb')).toBeNull();
		expect(screen.queryByText(/★/)).toBeNull();
	});

	it('hides the line when there is neither a rating nor an IMDb id', () => {
		renderComponent(MatchDetailPane, { props: withFacts({ rating: null }) });
		expect(screen.queryByText(/★/)).toBeNull();
		expect(screen.queryByText('Rating')).toBeNull();
		expect(screen.queryByText('IMDb')).toBeNull();
	});
});
