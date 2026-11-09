import { describe, it, expect } from 'vitest';
import { buildResolveBody, tvSeasonOrDiscChanged } from '$lib/utils/job-resolve';

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
