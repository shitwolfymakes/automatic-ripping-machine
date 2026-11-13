import { describe, it, expect } from 'vitest';
import type { JobView } from '$lib/types/api.gen';
import {
	appliedSessionName,
	discFactsLine,
	episodeMatchingDetail,
	matchDetailLine,
	matchProviderLabel,
	reviewSourceRow,
	reviewStatusLabel,
	type StatusLabelFlags
} from '../review-card';

const none: StatusLabelFlags = { previouslyRipped: false, suggestion: false, reviewGate: false, postRip: false };

describe('reviewStatusLabel', () => {
	it('says Awaiting Review when no flag is set', () => {
		expect(reviewStatusLabel(none)).toBe('Awaiting Review');
	});
	it('says Ripped when only postRip is set', () => {
		expect(reviewStatusLabel({ ...none, postRip: true })).toBe('Ripped: Apply Session');
	});
	it('says Ready when only reviewGate is set', () => {
		expect(reviewStatusLabel({ ...none, reviewGate: true })).toBe('Ready: Review & Start');
	});
	it('says Confirm the title when only suggestion is set', () => {
		expect(reviewStatusLabel({ ...none, suggestion: true })).toBe('Confirm the title: use it or search');
	});
	it('says Already ripped when only previouslyRipped is set', () => {
		expect(reviewStatusLabel({ ...none, previouslyRipped: true })).toBe('Already ripped: Rip again or Discard');
	});
	it('lets previouslyRipped win over every other flag', () => {
		expect(reviewStatusLabel({ previouslyRipped: true, suggestion: true, reviewGate: true, postRip: true })).toBe(
			'Already ripped: Rip again or Discard'
		);
	});
	it('lets suggestion win over reviewGate and postRip', () => {
		expect(reviewStatusLabel({ ...none, suggestion: true, reviewGate: true, postRip: true })).toBe(
			'Confirm the title: use it or search'
		);
	});
	it('lets reviewGate win over postRip', () => {
		expect(reviewStatusLabel({ ...none, reviewGate: true, postRip: true })).toBe('Ready: Review & Start');
	});
});

describe('episodeMatchingDetail', () => {
	it('gives the source and both counts', () => {
		expect(episodeMatchingDetail({ source: 'TMDb', total: 6, unmatched: 2 })).toBe('TMDb, 4 of 6 titles');
	});
	it('gives the counts alone when no source is known', () => {
		expect(episodeMatchingDetail({ source: null, total: 6, unmatched: 2 })).toBe('4 of 6 titles');
	});
	it('gives the source alone when unmatched is null', () => {
		expect(episodeMatchingDetail({ source: 'TMDb', total: 6, unmatched: null })).toBe('TMDb');
	});
	it('leaves the counts out when total is 0', () => {
		expect(episodeMatchingDetail({ source: 'TMDb', total: 0, unmatched: 0 })).toBe('TMDb');
	});
	it('leaves the counts out when total is null', () => {
		expect(episodeMatchingDetail({ source: 'TMDb', total: null, unmatched: 2 })).toBe('TMDb');
	});
	it('gives null when nothing is known', () => {
		expect(episodeMatchingDetail({ source: null, total: null, unmatched: null })).toBeNull();
	});
});

describe('matchDetailLine', () => {
	const withEnd = (year: number | null, end?: number | null) =>
		({ year, metadata_json: { identity: { facts: { end_year: end } } } }) as Pick<JobView, 'year' | 'metadata_json'>;

	it('gives the span for a TV series whose end year differs', () => {
		expect(matchDetailLine(withEnd(1974, 1975), true, undefined)).toBe('TV Series, 1974-1975');
	});
	it('gives one year when the end year equals the year', () => {
		expect(matchDetailLine(withEnd(1974, 1974), true, undefined)).toBe('TV Series, 1974');
	});
	it('gives one year when the end year is unset', () => {
		expect(matchDetailLine(withEnd(1974, null), true, undefined)).toBe('TV Series, 1974');
	});
	it('gives only the kind for TV with no year', () => {
		expect(matchDetailLine(withEnd(null), true, undefined)).toBe('TV Series');
	});
	it('leaves the years out when only an end year is set', () => {
		expect(matchDetailLine(withEnd(null, 1975), true, undefined)).toBe('TV Series');
	});
	it('gives the video type label and the year off TV', () => {
		expect(matchDetailLine(withEnd(1999), false, 'movie')).toBe('Movie, 1999');
	});
	it('gives an empty string with no video type and no year', () => {
		expect(matchDetailLine(withEnd(null), false, undefined)).toBe('');
	});
	it('copes with no metadata_json at all', () => {
		const job = { year: 2001 } as Pick<JobView, 'year' | 'metadata_json'>;
		expect(matchDetailLine(job, false, 'movie')).toBe('Movie, 2001');
	});
});

describe('matchProviderLabel', () => {
	const withIdentity = (identity: unknown) => ({ metadata_json: { identity } }) as Pick<JobView, 'metadata_json'>;

	it('gives null with no metadata_json', () => {
		expect(matchProviderLabel({} as Pick<JobView, 'metadata_json'>)).toBeNull();
	});
	it('gives null with no identity', () => {
		expect(matchProviderLabel({ metadata_json: {} })).toBeNull();
	});
	it('gives null with no provider', () => {
		expect(matchProviderLabel(withIdentity({}))).toBeNull();
	});
	it('gives null for a manual match', () => {
		expect(matchProviderLabel(withIdentity({ provider: 'manual' }))).toBeNull();
	});
	it('gives the label for a known provider', () => {
		expect(matchProviderLabel(withIdentity({ provider: 'tmdb' }))).toBe('TMDb');
	});
	it('shows an unknown provider as itself', () => {
		expect(matchProviderLabel(withIdentity({ provider: 'acme' }))).toBe('acme');
	});
});

describe('discFactsLine', () => {
	const disc = { disc_type: 'bluray', disc_number: null, disc_total: null } as const;
	it('joins the type, the disc number with its total and the title count', () => {
		expect(discFactsLine({ ...disc, disc_number: 1, disc_total: 4 }, 6)).toBe('Blu-ray, Disc 1/4, 6 titles');
	});
	it('shows a disc number with no total as "Disc n"', () => {
		expect(discFactsLine({ ...disc, disc_number: 2 }, 6)).toBe('Blu-ray, Disc 2, 6 titles');
	});
	it('leaves out the disc number when there is none', () => {
		expect(discFactsLine({ ...disc, disc_total: 4 }, 6)).toBe('Blu-ray, 6 titles');
	});
	it('leaves out the titles part for a count of 0', () => {
		expect(discFactsLine({ ...disc, disc_number: 1, disc_total: 4 }, 0)).toBe('Blu-ray, Disc 1/4');
	});
	it('leaves out the titles part when the count is undefined', () => {
		expect(discFactsLine(disc, undefined)).toBe('Blu-ray');
	});
	it('says Unknown with no disc type', () => {
		expect(discFactsLine({ ...disc, disc_type: undefined } as unknown as typeof disc, undefined)).toBe('Unknown');
	});
});

describe('reviewSourceRow', () => {
	const drive = { drive_id: 'drv_1' };
	const names = { drv_1: 'Drive A' };
	it('names the drive when there is no ISO', () => {
		expect(reviewSourceRow(drive, null, null, names)).toEqual({ label: 'Drive', value: 'Drive A' });
	});
	it('gives an empty value with no ISO and no drive id', () => {
		expect(reviewSourceRow({ drive_id: null }, null, null, names)).toEqual({ label: 'Drive', value: '' });
	});
	it('labels an ISO source of kind iso as ISO', () => {
		expect(reviewSourceRow(drive, 'a.iso', { drv_1: 'iso' }, names)).toEqual({ label: 'ISO', value: 'a.iso' });
	});
	it('labels an ISO source of kind folder as Folder', () => {
		expect(reviewSourceRow(drive, 'movie', { drv_1: 'folder' }, names)).toEqual({ label: 'Folder', value: 'movie' });
	});
	it('labels an ISO with no kind entry as ISO', () => {
		expect(reviewSourceRow(drive, 'a.iso', { other: 'folder' }, names)).toEqual({ label: 'ISO', value: 'a.iso' });
	});
	it('labels an ISO with no kinds map as ISO', () => {
		expect(reviewSourceRow(drive, 'a.iso', undefined, names)).toEqual({ label: 'ISO', value: 'a.iso' });
	});
	it('shows an empty ISO name as itself under Drive', () => {
		expect(reviewSourceRow(drive, '', null, names)).toEqual({ label: 'Drive', value: '' });
	});
	it('shows an ISO name with no drive id under Drive', () => {
		expect(reviewSourceRow({ drive_id: null }, 'a.iso', null, names)).toEqual({ label: 'Drive', value: 'a.iso' });
	});
});

describe('appliedSessionName', () => {
	const names = new Map([['ses_a', 'Plex 1080p']]);
	it('prefers the parked line over a pending id', () => {
		expect(appliedSessionName('Plex 1080p, waiting', 'ses_a', names)).toBe('Plex 1080p, waiting');
	});
	it('gives null with no parked line and no pending id', () => {
		expect(appliedSessionName(null, undefined, names)).toBeNull();
	});
	it('gives the name of a known pending session', () => {
		expect(appliedSessionName(null, 'ses_a', names)).toBe('Plex 1080p');
	});
	it('shows an unknown short pending id as itself', () => {
		expect(appliedSessionName(null, 'ses_b', names)).toBe('ses_b');
	});
	it('shortens an unknown pending id longer than 15 characters', () => {
		expect(appliedSessionName(null, 'ses_0123456789abcdef', names)).toBe('ses_0123456789a...');
	});
});
