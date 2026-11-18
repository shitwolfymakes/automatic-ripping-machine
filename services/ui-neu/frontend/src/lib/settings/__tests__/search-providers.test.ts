import { describe, it, expect } from 'vitest';
import {
	SEARCH_SOURCES,
	chooseSource,
	effectiveMovieProvider,
	sourceKeyed,
	type SearchSource
} from '../search-providers';

const ALL_KEYED = { tmdb: true, omdb: true, tvdb: true };
const NONE_KEYED = { tmdb: false, omdb: false, tvdb: false };

describe('SEARCH_SOURCES', () => {
	it('offers each search type its sources in picker order', () => {
		expect(SEARCH_SOURCES.movie.map((o) => o.id)).toEqual(['tmdb', 'omdb']);
		expect(SEARCH_SOURCES.tv.map((o) => o.id)).toEqual(['tmdb', 'omdb', 'tvmaze', 'tvdb']);
		expect(SEARCH_SOURCES.tv.map((o) => o.label)).toEqual(['TMDb', 'OMDb', 'TVmaze', 'TVDB']);
	});
});

describe('sourceKeyed', () => {
	it('needs no key for TVmaze', () => {
		expect(sourceKeyed('tvmaze', NONE_KEYED)).toBe(true);
	});

	it.each(['tmdb', 'omdb', 'tvdb'] as const)('follows the saved key for %s', (id) => {
		expect(sourceKeyed(id, ALL_KEYED)).toBe(true);
		expect(sourceKeyed(id, NONE_KEYED)).toBe(false);
	});
});

describe('chooseSource', () => {
	const tv = SEARCH_SOURCES.tv;
	const movie = SEARCH_SOURCES.movie;

	it('returns the pick while the type offers it', () => {
		expect(chooseSource(tv, 'tvdb', 'tmdb', ALL_KEYED)).toBe('tvdb');
	});

	it('ignores a pick the type does not offer', () => {
		expect(chooseSource(movie, 'tvdb' as SearchSource, 'omdb', ALL_KEYED)).toBe('omdb');
	});

	it('uses the Settings default when it is keyed', () => {
		expect(chooseSource(tv, null, 'omdb', ALL_KEYED)).toBe('omdb');
	});

	it('starts on the first keyed source when the default key was removed', () => {
		expect(chooseSource(tv, null, 'tmdb', { tmdb: false, omdb: false, tvdb: true })).toBe('tvmaze');
		expect(chooseSource(movie, null, 'tmdb', { tmdb: false, omdb: true, tvdb: false })).toBe('omdb');
	});

	it('keeps the unkeyed default when no source is usable', () => {
		expect(chooseSource(movie, null, 'tmdb', NONE_KEYED)).toBe('tmdb');
	});

	it('has no source when the default is not one of the options', () => {
		expect(chooseSource(movie, null, 'tvmaze', ALL_KEYED)).toBeUndefined();
		expect(chooseSource(movie, null, null, ALL_KEYED)).toBeUndefined();
	});
});

describe('effectiveMovieProvider', () => {
	it('honours the choice when its key is saved', () => {
		expect(effectiveMovieProvider({ search_provider_movie: 'omdb', omdb_api_key: 'k' })).toBe('omdb');
		expect(effectiveMovieProvider({ search_provider_movie: 'tmdb', tmdb_api_key: 'k' })).toBe('tmdb');
	});

	it('reports the fallback the backend will use when the chosen key is missing', () => {
		// The seeded default is tmdb, so an OMDb-only install must not be told TMDb.
		expect(effectiveMovieProvider({ search_provider_movie: 'tmdb', omdb_api_key: 'k' })).toBe('omdb');
		expect(effectiveMovieProvider({ search_provider_movie: 'omdb', tmdb_api_key: 'k' })).toBe('tmdb');
	});

	it('has no provider when neither movie key is saved', () => {
		// A TVDb-only install: the backend 400s a movie search, so the summary
		// must not name one.
		expect(effectiveMovieProvider({})).toBeNull();
		expect(effectiveMovieProvider({ search_provider_movie: 'omdb' })).toBeNull();
	});
});
