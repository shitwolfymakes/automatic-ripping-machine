import { describe, it, expect } from 'vitest';
import { discPosition, discKindLabel, jobTypeConfig, orderByLastModified, indexLogFiles, shortJobId } from './log-list';

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
		expect(discKindLabel({ ...base, disc_type: 'bluray', drive_id: 'drv_1' }, {})).toBe('Blu-ray');
	});
	it('names ISO and folder sources from the drive, retired drives included', () => {
		const kinds = { drv_iso: 'iso', drv_dir_retired: 'folder' } as const;
		expect(discKindLabel({ ...base, drive_id: 'drv_iso' }, kinds)).toBe('ISO');
		expect(discKindLabel({ ...base, drive_id: 'drv_dir_retired' }, kinds)).toBe('Folder');
	});
	it('falls back to the disc type with no drive or no map', () => {
		expect(discKindLabel({ ...base, drive_id: null }, { drv_iso: 'iso' })).toBe('DVD');
		expect(discKindLabel({ ...base, drive_id: 'drv_iso' })).toBe('DVD');
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

describe('indexLogFiles', () => {
	it('maps job id to modified_at, dropping unparseable dates', () => {
		const map = indexLogFiles([
			{ job_id: 'job_a', size_bytes: 1, modified_at: '2026-10-16T10:00:00Z' },
			{ job_id: 'job_b', size_bytes: 1, modified_at: 'garbage' }
		]);
		expect([...map.entries()]).toEqual([['job_a', '2026-10-16T10:00:00Z']]);
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

describe('shortJobId', () => {
	it('keeps job_ and the last four characters, lowercased', () => {
		expect(shortJobId('job_01JABCDEFGHJKMNPQRSTV9A41')).toBe('job_9a41');
	});
});
