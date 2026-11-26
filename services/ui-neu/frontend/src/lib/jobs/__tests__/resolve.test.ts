import { describe, it, expect } from 'vitest';
import {
	buildResolveBody,
	cdIdentifyBody,
	musicReleaseBody,
	titleMatchBody,
	titleResolveBody,
	tvSeasonOrDiscChanged,
	videoIdentifyBody
} from '$lib/jobs/resolve';

const job = (over: Record<string, unknown> = {}) =>
	({ id: 'j1', title: 'Show', year: 2020, media_type: 'tv', season: 1, disc_number: 2, ...over }) as any;

describe('buildResolveBody', () => {
	it('sets a trimmed title and keeps the job year', () => {
		expect(buildResolveBody(job(), 'title', '  New  ')).toEqual({ title: 'New', year: 2020 });
	});

	it('throws on a blank title', () => {
		expect(() => buildResolveBody(job(), 'title', '   ')).toThrow('A title is required');
	});

	it('sets the year and keeps the job title', () => {
		expect(buildResolveBody(job(), 'year', '1999')).toEqual({ title: 'Show', year: 1999 });
	});

	it('gives a null year for a blank year', () => {
		expect(buildResolveBody(job(), 'year', ' ')).toEqual({ title: 'Show', year: null });
	});

	it.each(['season', 'disc_number', 'disc_total'] as const)('sets and clears %s', (field) => {
		expect(buildResolveBody(job(), field, '3')).toEqual({ title: 'Show', year: 2020, [field]: 3 });
		expect(buildResolveBody(job(), field, '')).toEqual({ title: 'Show', year: 2020, [field]: null });
	});

	it("falls back to '' and null when the job has no title or year", () => {
		expect(buildResolveBody(job({ title: null, year: null }), 'season', '2')).toEqual({
			title: '',
			year: null,
			season: 2
		});
		expect(buildResolveBody(job({ title: undefined, year: undefined }), 'season', '')).toEqual({
			title: '',
			year: null,
			season: null
		});
	});
});

describe('cdIdentifyBody', () => {
	const cd = (over: Record<string, unknown> = {}) => ({
		album: '  Album ',
		artist: ' Artist  ',
		year: 1999,
		trackTitles: [' One ', 'Two  '],
		...over
	});

	it('trims album, artist and each track title', () => {
		expect(cdIdentifyBody(cd())).toEqual({
			title: 'Album',
			year: 1999,
			music: { artist: 'Artist', album: 'Album', tracks: [{ title: 'One' }, { title: 'Two' }] }
		});
	});

	it("keeps a blank track title as ''", () => {
		expect(cdIdentifyBody(cd({ trackTitles: ['  '] })).music?.tracks).toEqual([{ title: '' }]);
	});

	it('sends a null year as null', () => {
		expect(cdIdentifyBody(cd({ year: null })).year).toBeNull();
	});

	it('sends no tracks for an empty list', () => {
		expect(cdIdentifyBody(cd({ trackTitles: [] })).music?.tracks).toEqual([]);
	});
});

describe('videoIdentifyBody', () => {
	it('trims the title', () => {
		expect(videoIdentifyBody({ title: '  Movie ', year: null }).title).toBe('Movie');
	});

	it('sends a set year', () => {
		expect(videoIdentifyBody({ title: 'Movie', year: 2001 })).toEqual({ title: 'Movie', year: 2001 });
	});

	it('sends a null year as null', () => {
		expect(videoIdentifyBody({ title: 'Movie', year: null }).year).toBeNull();
	});

	it('has no music key', () => {
		expect(videoIdentifyBody({ title: 'Movie', year: 2001 })).not.toHaveProperty('music');
	});
});

describe('tvSeasonOrDiscChanged', () => {
	it('is false without an after job', () => {
		expect(tvSeasonOrDiscChanged(job(), undefined)).toBe(false);
		expect(tvSeasonOrDiscChanged(job(), null)).toBe(false);
	});

	it('is false for a movie', () => {
		expect(tvSeasonOrDiscChanged(job({ media_type: 'movie' }), job({ season: 5 }))).toBe(false);
	});

	it('is true when the season changed', () => {
		expect(tvSeasonOrDiscChanged(job(), job({ season: 2 }))).toBe(true);
	});

	it('is true when the disc changed', () => {
		expect(tvSeasonOrDiscChanged(job(), job({ disc_number: 3 }))).toBe(true);
	});

	it('is false when neither changed', () => {
		expect(tvSeasonOrDiscChanged(job(), job())).toBe(false);
	});

	it('treats a missing value as null on both sides', () => {
		const bare = { season: undefined, disc_number: undefined };
		expect(tvSeasonOrDiscChanged(job(bare), job({ season: null, disc_number: null }))).toBe(false);
		expect(tvSeasonOrDiscChanged(job(bare), job({ season: 1 }))).toBe(true);
		expect(tvSeasonOrDiscChanged(job({ season: null, disc_number: null }), job(bare))).toBe(false);
		expect(tvSeasonOrDiscChanged(job({ season: null, disc_number: null }), job({ disc_number: 1 }))).toBe(true);
	});
});

describe('musicReleaseBody', () => {
	const fields = (over: Record<string, string> = {}) => ({
		album: ' Album ',
		artist: ' Artist ',
		year: '1999',
		discNumber: '1',
		discTotal: '2',
		...over
	});

	it('trims the album as title and music.album, and the artist', () => {
		const body = musicReleaseBody(fields(), []);
		expect(body.title).toBe('Album');
		expect(body.music).toEqual({ artist: 'Artist', album: 'Album', tracks: [] });
	});

	it.each([
		['1999', 1999],
		[' 7 ', 7],
		['', null],
		['   ', null],
		['abc', null],
		['Infinity', null]
	])('parses the year, disc number and disc total from %j to %j', (raw, want) => {
		expect(musicReleaseBody(fields({ year: raw, discNumber: raw, discTotal: raw }), [])).toMatchObject({
			year: want,
			disc_number: want,
			disc_total: want
		});
	});

	it('maps each track, with a missing position, length and disc number null', () => {
		const body = musicReleaseBody(fields(), [
			{ position: 1, title: 'One', length_ms: 1000, disc_number: 2 },
			{ title: 'Two' }
		]);
		expect(body.music?.tracks).toEqual([
			{ position: 1, title: 'One', length_ms: 1000, disc_number: 2 },
			{ position: undefined, title: 'Two', length_ms: null, disc_number: null }
		]);
	});

	it('keeps the keys in order', () => {
		const body = musicReleaseBody(fields(), [{ position: 1, title: 'One' }]);
		expect(Object.keys(body)).toEqual(['title', 'year', 'disc_number', 'disc_total', 'music']);
		expect(Object.keys(body.music!)).toEqual(['artist', 'album', 'tracks']);
		expect(Object.keys(body.music!.tracks![0])).toEqual(['position', 'title', 'length_ms', 'disc_number']);
	});
});

const values = (over: Record<string, unknown> = {}) =>
	({ title: 'Heat', year: '1995', isSeries: false, poster: null, ...over }) as any;

const candidate = (over: Record<string, unknown> = {}) =>
	({ title: 'Heat', kind: 'movie', provider: 'tmdb', ...over }) as any;

describe('titleMatchBody', () => {
	it('states the whole show: every id, the provider, the poster and the facts', () => {
		const facts = { runtime: 170 };
		const c = candidate({
			external_ids: { imdb: 'tt0113277', tmdb: 949, tmdb_kind: 'movie', tvdb: 1, tvmaze: 2 },
			poster_url: 'https://img/p.jpg',
			facts
		});
		const body = titleMatchBody(c, values(), false);
		expect(body).toEqual({
			title: 'Heat',
			year: 1995,
			media_type: 'movie',
			external_ids: { imdb: 'tt0113277', tmdb: 949, tmdb_kind: 'movie', tvdb: 1, tvmaze: 2 },
			match: {
				provider: 'tmdb',
				poster_url: 'https://img/p.jpg',
				poster_is_manual: false,
				poster_url_manual: null,
				facts
			}
		});
		expect(Object.keys(body)).toEqual(['title', 'year', 'media_type', 'external_ids', 'match']);
		expect(Object.keys(body.external_ids!)).toEqual(['imdb', 'tmdb', 'tmdb_kind', 'tvdb', 'tvmaze']);
		expect(Object.keys(body.match!)).toEqual([
			'provider',
			'poster_url',
			'poster_is_manual',
			'poster_url_manual',
			'facts'
		]);
	});

	it('sends a null for each show id the match lacks', () => {
		const body = titleMatchBody(candidate({ external_ids: { tmdb: 949 } }), values(), false);
		expect(body.external_ids).toEqual({ imdb: null, tmdb: 949, tmdb_kind: null, tvdb: null, tvmaze: null });
	});

	it('sends every id null when external_ids is missing', () => {
		const body = titleMatchBody(candidate(), values(), false);
		expect(body.external_ids).toEqual({ imdb: null, tmdb: null, tmdb_kind: null, tvdb: null, tvmaze: null });
	});

	it('sends a null poster_url and null facts when the match lacks them', () => {
		const body = titleMatchBody(candidate(), values({ poster: 'https://edit/p.jpg' }), false);
		expect(body.match).toEqual({
			provider: 'tmdb',
			poster_url: null,
			poster_is_manual: false,
			poster_url_manual: null,
			facts: null
		});
	});

	it('sends the edited poster as the manual one, beside the row own poster', () => {
		const body = titleMatchBody(
			candidate({ poster_url: 'https://img/p.jpg' }),
			values({ poster: 'https://edit/p.jpg' }),
			true
		);
		expect(body.match).toMatchObject({
			poster_url: 'https://img/p.jpg',
			poster_is_manual: true,
			poster_url_manual: 'https://edit/p.jpg'
		});
	});

	it('sends a null manual poster when the edit cleared it', () => {
		const body = titleMatchBody(candidate(), values({ poster: null }), true);
		expect(body.match).toMatchObject({ poster_is_manual: true, poster_url_manual: null });
	});

	it.each([
		['', null],
		['abc', null],
		['Infinity', null],
		['1995', 1995]
	])('parses the year %j to %j', (year, want) => {
		expect(titleMatchBody(candidate(), values({ year }), false).year).toBe(want);
	});

	it.each([
		[true, 'tv'],
		[false, 'movie']
	])('sends the media type for isSeries %s as %s', (isSeries, want) => {
		expect(titleMatchBody(candidate(), values({ isSeries }), false).media_type).toBe(want);
	});
});

describe('titleResolveBody', () => {
	it('sends the title, the year and the media type in that order', () => {
		const body = titleResolveBody(values());
		expect(body).toEqual({ title: 'Heat', year: 1995, media_type: 'movie' });
		expect(Object.keys(body)).toEqual(['title', 'year', 'media_type']);
	});

	it.each([
		['', null],
		['abc', null],
		['1995', 1995]
	])('parses the year %j to %j', (year, want) => {
		expect(titleResolveBody(values({ year })).year).toBe(want);
	});

	it.each([
		[true, 'tv'],
		[false, 'movie']
	])('sends the media type for isSeries %s as %s', (isSeries, want) => {
		expect(titleResolveBody(values({ isSeries })).media_type).toBe(want);
	});
});
