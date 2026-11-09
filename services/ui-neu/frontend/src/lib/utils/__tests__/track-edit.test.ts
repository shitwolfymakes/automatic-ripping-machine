import { describe, it, expect } from 'vitest';
import { parseEpisodeNumber, trackOptionsBody, trackTitleBody } from '../track-edit';

describe('parseEpisodeNumber', () => {
	it.each([
		['3', 3],
		[' 4 ', 4],
		['1e2', 100],
		['0', 0],
		['-2', -2]
	])('parses %j as the number %d', (raw, expected) => {
		expect(parseEpisodeNumber(raw)).toBe(expected);
	});

	it.each([[''], ['   ']])('gives null for the blank %j', (raw) => {
		expect(parseEpisodeNumber(raw)).toBeNull();
	});

	it.each([['abc'], ['Infinity'], ['-Infinity']])('gives null for the non-finite %j', (raw) => {
		expect(parseEpisodeNumber(raw)).toBeNull();
	});
});

const opts = { filename: '', episodeNumber: '', episodeName: '' };

describe('trackOptionsBody', () => {
	it('trims the custom filename', () => {
		const body = trackOptionsBody({ ...opts, filename: '  out.mkv  ' }, false);
		expect(body).toEqual({ custom_filename: 'out.mkv' });
	});

	it('sends a null filename when blank', () => {
		const body = trackOptionsBody({ ...opts, filename: '   ' }, false);
		expect(body).toEqual({ custom_filename: null });
	});

	it('sends no episode keys on a non-series track', () => {
		const body = trackOptionsBody({ filename: 'a', episodeNumber: '3', episodeName: 'Pilot' }, false);
		expect(Object.keys(body)).toEqual(['custom_filename']);
	});

	it('sends the episode number and trimmed name on a series track', () => {
		const body = trackOptionsBody({ filename: 'a', episodeNumber: ' 3 ', episodeName: '  Pilot ' }, true);
		expect(body).toEqual({ custom_filename: 'a', episode_number: 3, episode_name: 'Pilot' });
		expect(Object.keys(body)).toEqual(['custom_filename', 'episode_number', 'episode_name']);
	});

	it('sends null episode number and name when blank on a series track', () => {
		const body = trackOptionsBody({ ...opts, episodeNumber: '  ', episodeName: '  ' }, true);
		expect(body).toEqual({ custom_filename: null, episode_number: null, episode_name: null });
	});

	it('sends a null episode number when it is not a number', () => {
		const body = trackOptionsBody({ ...opts, episodeNumber: 'abc' }, true);
		expect(body).toEqual({ custom_filename: null, episode_number: null, episode_name: null });
	});

	it('sends a null episode number when it is Infinity', () => {
		const body = trackOptionsBody({ ...opts, episodeNumber: 'Infinity' }, true);
		expect(body).toEqual({ custom_filename: null, episode_number: null, episode_name: null });
	});

	it('sends an exponent episode number as a number', () => {
		const body = trackOptionsBody({ ...opts, episodeNumber: '1e2' }, true);
		expect(body).toEqual({ custom_filename: null, episode_number: 100, episode_name: null });
	});

	it('sends a padded episode number as a number', () => {
		const body = trackOptionsBody({ ...opts, episodeNumber: ' 7 ' }, true);
		expect(body).toEqual({ custom_filename: null, episode_number: 7, episode_name: null });
	});
});

describe('trackTitleBody', () => {
	const title = { title: ' Alien ', year: ' 1979 ', type: 'movie' as const, posterUrl: ' p.jpg ' };

	it('trims the title and poster, sends the year as a number, role main for Movie', () => {
		const body = trackTitleBody(title);
		expect(body).toEqual({ title: 'Alien', year: 1979, role: 'main', poster_url: 'p.jpg' });
		expect(Object.keys(body)).toEqual(['title', 'year', 'role', 'poster_url']);
	});

	it('sends role episode for Series', () => {
		expect(trackTitleBody({ ...title, type: 'series' }).role).toBe('episode');
	});

	it('sends an undefined year when blank', () => {
		expect(trackTitleBody({ ...title, year: '  ' }).year).toBeUndefined();
	});

	it('sends an undefined year when it is not a number', () => {
		expect(trackTitleBody({ ...title, year: 'abc' }).year).toBeUndefined();
	});

	it('sends an undefined poster when blank', () => {
		expect(trackTitleBody({ ...title, posterUrl: '  ' }).poster_url).toBeUndefined();
	});
});
