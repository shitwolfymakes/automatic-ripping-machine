import { describe, it, expect } from 'vitest';
import { effectiveMovieProvider, providerLabel } from './search-providers';

describe('providerLabel', () => {
	it('names each provider and falls back until the config store hydrates', () => {
		expect(providerLabel('tmdb')).toBe('TMDb');
		expect(providerLabel('omdb')).toBe('OMDb');
		expect(providerLabel('tvmaze')).toBe('TVmaze');
		expect(providerLabel('tvdb')).toBe('TVDB');
		expect(providerLabel(null)).toBe('OMDb/TMDb');
		expect(providerLabel('bogus', 'TMDb')).toBe('TMDb');
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
