import { describe, it, expect } from 'vitest';
import {
	discPosition,
	discKindLabel,
	jobTypeConfig,
	formatShortDateTime,
	orderByLastModified,
	logRelativeTime,
	shortJobId
} from './log-list';

const base = { metadata_json: {}, disc_type: 'dvd', media_type: null } as const;

describe('discPosition', () => {
	it('joins season and disc of total', () => {
		expect(discPosition({ season: 1, disc_number: 1, disc_total: 4 })).toBe('S1 · Disc 1/4');
	});
	it('omits the parts that are unknown', () => {
		expect(discPosition({ season: null, disc_number: 2, disc_total: 4 })).toBe('Disc 2/4');
		expect(discPosition({ season: 1, disc_number: null, disc_total: null })).toBe('S1');
		expect(discPosition({ season: 1, disc_number: 2, disc_total: null })).toBe('S1 · Disc 2');
	});
	it('drops a total with no disc number', () => {
		expect(discPosition({ season: 2, disc_number: null, disc_total: 4 })).toBe('S2');
	});
	it('is a dash when nothing is known', () => {
		expect(discPosition({})).toBe('-');
	});
});

describe('discKindLabel', () => {
	it('uses the disc type label', () => {
		expect(discKindLabel({ ...base, disc_type: 'bluray' })).toBe('Blu-ray');
	});
	it('names ISO and folder sources', () => {
		const iso = { provider_raw: { arm_server: { source_type: 'iso' } } };
		const folder = { provider_raw: { arm_server: { source_type: 'folder' } } };
		expect(discKindLabel({ ...base, metadata_json: iso })).toBe('ISO');
		expect(discKindLabel({ ...base, metadata_json: folder })).toBe('Folder');
	});
});

describe('jobTypeConfig', () => {
	it('maps media types to the type labels', () => {
		expect(jobTypeConfig({ ...base, media_type: 'tv' }).label).toBe('Series');
		expect(jobTypeConfig({ ...base, media_type: 'movie' }).label).toBe('Movie');
	});
	it('treats CDs as music', () => {
		expect(jobTypeConfig({ ...base, disc_type: 'cd' }).label).toBe('Music');
	});
});

describe('formatShortDateTime', () => {
	it('formats month, day and time', () => {
		const out = formatShortDateTime('2026-10-16T12:18:00Z');
		expect(out).toMatch(/Oct 1[56]/);
		expect(out).toMatch(/\d{1,2}:18/);
	});
});

describe('orderByLastModified', () => {
	it('puts newest logs first and jobs without a log after, in job order', () => {
		const jobs = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }];
		const mod = new Map([
			['b', '2026-10-15T10:00:00Z'],
			['d', '2026-10-16T10:00:00Z']
		]);
		expect(orderByLastModified(jobs, mod).map((j) => j.id)).toEqual(['d', 'b', 'a', 'c']);
	});
});

describe('logRelativeTime', () => {
	// Fixed local "now": Oct 16 2026, 12:00
	const now = new Date(2026, 9, 16, 12, 0, 0);
	const at = (...args: [number, number, number, number, number]) => new Date(...args).toISOString();

	it('says just now under a minute', () => {
		expect(logRelativeTime(new Date(now.getTime() - 30_000).toISOString(), now)).toBe('Just now');
	});
	it('counts minutes, then hours the same day', () => {
		expect(logRelativeTime(at(2026, 9, 16, 11, 18), now)).toBe('42 min ago');
		expect(logRelativeTime(at(2026, 9, 16, 9, 0), now)).toBe('3h ago');
		expect(logRelativeTime(at(2026, 9, 16, 0, 5), now)).toBe('11h ago');
	});
	it('says yesterday for the previous calendar day', () => {
		expect(logRelativeTime(at(2026, 9, 15, 23, 0), now)).toBe('Yesterday');
		expect(logRelativeTime(at(2026, 9, 15, 0, 1), now)).toBe('Yesterday');
	});
	it('counts days up to six', () => {
		expect(logRelativeTime(at(2026, 9, 14, 20, 0), now)).toBe('2 days ago');
		expect(logRelativeTime(at(2026, 9, 10, 1, 0), now)).toBe('6 days ago');
	});
	it('is null past six days, so only the absolute date shows', () => {
		expect(logRelativeTime(at(2026, 9, 9, 23, 0), now)).toBeNull();
	});
	it('counts minutes across midnight before calendar days', () => {
		const justAfterMidnight = new Date(2026, 9, 16, 0, 10);
		expect(logRelativeTime(at(2026, 9, 15, 23, 50), justAfterMidnight)).toBe('20 min ago');
	});
});

describe('shortJobId', () => {
	it('keeps job_ and the last four characters, lowercased', () => {
		expect(shortJobId('job_01JABCDEFGHJKMNPQRSTV9A41')).toBe('job_9a41');
	});
});
