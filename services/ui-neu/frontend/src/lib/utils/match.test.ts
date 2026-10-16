import { describe, it, expect } from 'vitest';
import type { MetadataCandidate } from '$lib/types/api.gen';
import { candidateKey, detailsId, formatVotes, formatYears, isSeriesKind, kindLabel, mergeCandidate } from './match';

const cand = (o: Partial<MetadataCandidate> = {}): MetadataCandidate => ({ title: 'K', kind: 'tv', ...o });

describe('match utils', () => {
	it('isSeriesKind', () => {
		expect([isSeriesKind('tv'), isSeriesKind('series'), isSeriesKind('movie')]).toEqual([true, true, false]);
	});

	it('formatYears', () => {
		expect(formatYears(1974, 1975, 'tv')).toBe('1974–1975');
		expect(formatYears(1974, 1974, 'tv')).toBe('1974');
		expect(formatYears(2005, null, 'tv')).toBe('2005');
		expect(formatYears(1972, 1999, 'movie')).toBe('1972');
		expect(formatYears(null, 1975, 'tv')).toBe('');
	});

	it('kindLabel', () => {
		expect(kindLabel('tv')).toBe('TV Series');
		expect(kindLabel('series')).toBe('TV Series');
		expect(kindLabel('movie')).toBe('Movie');
	});

	it('formatVotes', () => {
		expect(formatVotes(1)).toBe('1 vote');
		expect(formatVotes(950)).toBe('950 votes');
		expect(formatVotes(9812)).toBe('9.8K votes');
		expect(formatVotes(12000)).toBe('12K votes');
		expect(formatVotes(1_250_000)).toBe('1.3M votes');
	});

	it('detailsId picks the provider-native id', () => {
		const ids = { imdb: 'tt1', tmdb: '5', tvdb: '9', tvmaze: '7' };
		expect(detailsId(cand({ provider: 'tmdb', external_ids: ids }))).toBe('5');
		expect(detailsId(cand({ provider: 'omdb', external_ids: ids }))).toBe('tt1');
		expect(detailsId(cand({ provider: 'omdb', provider_id: 'tt2' }))).toBe('tt2');
		expect(detailsId(cand({ provider: 'tvmaze', external_ids: ids }))).toBe('7');
		expect(detailsId(cand({ provider: 'tvdb', external_ids: ids }))).toBe('9');
		expect(detailsId(cand({ provider: null, external_ids: ids }))).toBeNull();
		expect(detailsId(cand({ provider: 'tvdb' }))).toBeNull();
	});

	it('candidateKey is stable per provider and id', () => {
		expect(candidateKey(cand({ provider: 'tvmaze', external_ids: { tvmaze: '7' } }))).toBe('tvmaze:7');
		expect(candidateKey(cand({ provider: null, title: 'X', year: 1999 }))).toBe(':X:1999');
	});

	it('mergeCandidate prefers detail values and keeps row values the detail lacks', () => {
		const row = cand({
			poster_url: 'row.jpg',
			external_ids: { imdb: 'tt1', tvmaze: '7' },
			facts: { genres: ['Horror'], cast: [], creators: [], rating: 8, rating_source: 'tvmaze' }
		});
		const detail = cand({
			poster_url: null,
			external_ids: { imdb: null, tvdb: '9' },
			facts: { genres: [], cast: ['Darren McGavin'], creators: [], episode_count: 20 }
		});
		const m = mergeCandidate(row, detail);
		expect(m.poster_url).toBe('row.jpg');
		expect(m.external_ids).toMatchObject({ imdb: 'tt1', tvmaze: '7', tvdb: '9' });
		expect(m.facts).toMatchObject({
			genres: ['Horror'],
			cast: ['Darren McGavin'],
			rating: 8,
			rating_source: 'tvmaze',
			episode_count: 20
		});
	});
});
