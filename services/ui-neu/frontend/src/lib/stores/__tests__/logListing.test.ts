import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchAllJobsMock = vi.fn();
const fetchJobLogIndexMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	fetchAllJobs: (...a: unknown[]) => fetchAllJobsMock(...a)
}));
vi.mock('$lib/api/logs', () => ({
	fetchJobLogIndex: (...a: unknown[]) => fetchJobLogIndexMock(...a)
}));

import { LogListing } from '$lib/stores/log-listing.svelte';

const JOBS = [{ id: 'j1' }, { id: 'j2' }];

beforeEach(() => {
	fetchAllJobsMock.mockReset();
	fetchJobLogIndexMock.mockReset();
});

describe('LogListing', () => {
	it('starts empty, loading and without an error', () => {
		const listing = new LogListing();
		expect(listing.jobs).toEqual([]);
		expect(listing.total).toBe(0);
		expect(listing.modified.size).toBe(0);
		expect(listing.loading).toBe(true);
		expect(listing.error).toBeNull();
	});

	it('load stores the jobs, the total and the modified map, and lowers loading', async () => {
		fetchAllJobsMock.mockResolvedValue({ jobs: JOBS, total: 2 });
		fetchJobLogIndexMock.mockResolvedValue([{ job_id: 'j1', modified_at: '2026-01-02T03:04:05Z' }]);
		const listing = new LogListing();
		await listing.load();
		expect(listing.jobs).toEqual(JOBS);
		expect(listing.total).toBe(2);
		expect(listing.modified.get('j1')).toBe('2026-01-02T03:04:05Z');
		expect(listing.modified.size).toBe(1);
		expect(listing.loading).toBe(false);
		expect(listing.error).toBeNull();
	});

	it('load still lists the jobs with an empty map when the index fails', async () => {
		fetchAllJobsMock.mockResolvedValue({ jobs: JOBS, total: 2 });
		fetchJobLogIndexMock.mockRejectedValue(new Error('index down'));
		const listing = new LogListing();
		await listing.load();
		expect(listing.jobs).toEqual(JOBS);
		expect(listing.modified.size).toBe(0);
		expect(listing.loading).toBe(false);
		expect(listing.error).toBeNull();
	});

	it('load keeps the Error when the jobs fail, and still reads the index', async () => {
		const boom = new Error('jobs down');
		fetchAllJobsMock.mockRejectedValue(boom);
		fetchJobLogIndexMock.mockResolvedValue([{ job_id: 'j1', modified_at: '2026-01-02T03:04:05Z' }]);
		const listing = new LogListing();
		await listing.load();
		expect(listing.error).toBe(boom);
		expect(listing.jobs).toEqual([]);
		expect(listing.modified.size).toBe(1);
		expect(listing.loading).toBe(false);
	});

	it('load wraps a non-Error rejection of the jobs in an Error', async () => {
		fetchAllJobsMock.mockRejectedValue('plain failure');
		fetchJobLogIndexMock.mockResolvedValue([]);
		const listing = new LogListing();
		await listing.load();
		expect(listing.error).toBeInstanceOf(Error);
		expect(listing.error?.message).toBe('plain failure');
		expect(listing.loading).toBe(false);
	});

	it('load records the error and an empty map when both requests fail', async () => {
		fetchAllJobsMock.mockRejectedValue(new Error('jobs down'));
		fetchJobLogIndexMock.mockRejectedValue(new Error('index down'));
		const listing = new LogListing();
		await listing.load();
		expect(listing.error?.message).toBe('jobs down');
		expect(listing.jobs).toEqual([]);
		expect(listing.modified.size).toBe(0);
		expect(listing.loading).toBe(false);
	});
});
