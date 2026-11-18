import { describe, it, expect } from 'vitest';
import type { JobView } from '$lib/types/api.gen';
import {
	discPosition,
	discKindLabel,
	jobTypeConfig,
	orderByLastModified,
	indexLogFiles,
	shortJobId,
	filterLogJobs,
	logCountText
} from '../list';

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

describe('filterLogJobs', () => {
	const jobs: Pick<JobView, 'id' | 'status' | 'title'>[] = [
		{ id: 'job_AAA1', status: 'ripped', title: 'Alien' },
		{ id: 'job_BBB2', status: 'failed', title: 'Blade Runner' },
		{ id: 'job_CCC3', status: 'ripped', title: null },
		{ id: 'job_DDD4', status: 'failed', title: 'Alien Nation' }
	];
	const ids = (list: { id: string }[]) => list.map((j) => j.id);

	it('keeps every job, in order, with no filter and no search', () => {
		expect(ids(filterLogJobs(jobs, '', ''))).toEqual(['job_AAA1', 'job_BBB2', 'job_CCC3', 'job_DDD4']);
	});
	it('keeps only the jobs with the filtered status', () => {
		expect(ids(filterLogJobs(jobs, 'failed', ''))).toEqual(['job_BBB2', 'job_DDD4']);
	});
	it('matches the search against the title', () => {
		expect(ids(filterLogJobs(jobs, '', 'runner'))).toEqual(['job_BBB2']);
	});
	it('matches the search against the id', () => {
		expect(ids(filterLogJobs(jobs, '', 'bbb2'))).toEqual(['job_BBB2']);
	});
	it('ignores case in the search', () => {
		expect(ids(filterLogJobs(jobs, '', 'ALIEN'))).toEqual(['job_AAA1', 'job_DDD4']);
	});
	it('finds a job with no title by its id', () => {
		expect(ids(filterLogJobs(jobs, '', 'ccc3'))).toEqual(['job_CCC3']);
	});
	it('applies the status filter and the search together', () => {
		expect(ids(filterLogJobs(jobs, 'failed', 'alien'))).toEqual(['job_DDD4']);
	});
	it('returns nothing when no job matches', () => {
		expect(filterLogJobs(jobs, 'ripped', 'blade')).toEqual([]);
	});
});

describe('logCountText', () => {
	it('shows the total with a noun that follows it when not filtering', () => {
		expect(logCountText(0, 0, false)).toBe('0 jobs');
		expect(logCountText(1, 1, false)).toBe('1 job');
		expect(logCountText(2, 2, false)).toBe('2 jobs');
	});
	it('shows shown of total while filtering, the noun following the total', () => {
		expect(logCountText(1, 3, true)).toBe('1 of 3 jobs');
		expect(logCountText(0, 1, true)).toBe('0 of 1 job');
	});
});

describe('shortJobId', () => {
	it('keeps job_ and the last four characters, lowercased', () => {
		expect(shortJobId('job_01JABCDEFGHJKMNPQRSTV9A41')).toBe('job_9a41');
	});
});
