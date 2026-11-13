import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { JobView } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({ fetchJobsPage: vi.fn() }));

import { fetchJobsPage } from '$lib/api/jobs';
import { DashboardJobs, JOBS_PER_PAGE } from '../dashboard-jobs.svelte';

const mockFetch = vi.mocked(fetchJobsPage);

const job = (id: string) => ({ id }) as JobView;
const pageOf = (ids: string[], total = ids.length) => ({ jobs: ids.map(job), total });

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	mockFetch.mockReset();
});

describe('DashboardJobs', () => {
	it('starts empty, loading, on page 1 with 48 per page', () => {
		const list = new DashboardJobs();
		expect(JOBS_PER_PAGE).toBe(48);
		expect(list.perPage).toBe(48);
		expect(list.jobs).toBeNull();
		expect(list.loading).toBe(true);
		expect(list.page).toBe(1);
		expect(list.pages).toBe(1);
		expect(list.allVisibleSelected).toBe(false);
	});

	it('requests the first page with no status when the filter is empty', async () => {
		mockFetch.mockResolvedValue(pageOf(['a']));
		await new DashboardJobs().load();
		expect(mockFetch).toHaveBeenCalledWith({ status: undefined, limit: 48, offset: 0 });
	});

	it('requests the status filter and the page offset', async () => {
		mockFetch.mockResolvedValue(pageOf(['a'], 100));
		const list = new DashboardJobs();
		list.statusFilter = 'ripping';
		list.page = 2;
		await list.load();
		expect(mockFetch).toHaveBeenCalledWith({ status: 'ripping', limit: 48, offset: 48 });
	});

	it('stores the page, the total and the page count on success', async () => {
		mockFetch.mockResolvedValue(pageOf(['a', 'b'], 100));
		const list = new DashboardJobs();
		await list.load();
		expect(list.jobs?.map((j) => j.id)).toEqual(['a', 'b']);
		expect(list.total).toBe(100);
		expect(list.pages).toBe(3);
		expect(list.loading).toBe(false);
		expect(list.error).toBeNull();
	});

	it('shows loading only while there are no jobs yet', async () => {
		mockFetch.mockResolvedValue(pageOf(['a']));
		const list = new DashboardJobs();
		await list.load();
		const second = deferred<ReturnType<typeof pageOf>>();
		mockFetch.mockReturnValue(second.promise);
		const pending = list.load();
		expect(list.loading).toBe(false);
		second.resolve(pageOf(['a']));
		await pending;
		expect(list.loading).toBe(false);
	});

	it('is loading during the first load', async () => {
		const first = deferred<ReturnType<typeof pageOf>>();
		mockFetch.mockReturnValue(first.promise);
		const list = new DashboardJobs();
		list.loading = false;
		const pending = list.load();
		expect(list.loading).toBe(true);
		first.resolve(pageOf([]));
		await pending;
		expect(list.loading).toBe(false);
	});

	it('keeps an Error from a failed load', async () => {
		const err = new Error('boom');
		mockFetch.mockRejectedValue(err);
		const list = new DashboardJobs();
		await list.load();
		expect(list.error).toBe(err);
		expect(list.loading).toBe(false);
	});

	it('wraps a non-Error failure in a generic Error', async () => {
		mockFetch.mockRejectedValue('nope');
		const list = new DashboardJobs();
		await list.load();
		expect(list.error?.message).toBe('Failed to load jobs');
	});

	it('clears the error when a new load starts', async () => {
		mockFetch.mockRejectedValueOnce(new Error('x'));
		const list = new DashboardJobs();
		await list.load();
		mockFetch.mockResolvedValue(pageOf(['a']));
		await list.load();
		expect(list.error).toBeNull();
	});

	it('drops a stale response on success', async () => {
		const slow = deferred<ReturnType<typeof pageOf>>();
		mockFetch.mockReturnValueOnce(slow.promise);
		const list = new DashboardJobs();
		const first = list.load();
		mockFetch.mockResolvedValueOnce(pageOf(['new']));
		await list.load();
		slow.resolve(pageOf(['old']));
		await first;
		expect(list.jobs?.map((j) => j.id)).toEqual(['new']);
		expect(list.loading).toBe(false);
	});

	it('drops a stale failure', async () => {
		const slow = deferred<ReturnType<typeof pageOf>>();
		mockFetch.mockReturnValueOnce(slow.promise);
		const list = new DashboardJobs();
		const first = list.load();
		mockFetch.mockResolvedValueOnce(pageOf(['new']));
		await list.load();
		slow.reject(new Error('late'));
		await first;
		expect(list.error).toBeNull();
		expect(list.jobs?.map((j) => j.id)).toEqual(['new']);
	});

	it('steps back to the last page that has rows when the page empties', async () => {
		mockFetch.mockResolvedValueOnce(pageOf([], 50)).mockResolvedValueOnce(pageOf(['z'], 50));
		const list = new DashboardJobs();
		list.page = 5;
		await list.load();
		expect(list.page).toBe(2);
		expect(mockFetch).toHaveBeenCalledTimes(2);
		expect(mockFetch).toHaveBeenLastCalledWith({ status: undefined, limit: 48, offset: 48 });
		expect(list.jobs?.map((j) => j.id)).toEqual(['z']);
	});

	it('stays put on an empty first page', async () => {
		mockFetch.mockResolvedValue(pageOf([], 0));
		const list = new DashboardJobs();
		await list.load();
		expect(mockFetch).toHaveBeenCalledTimes(1);
		expect(list.page).toBe(1);
	});

	it('stays put on an empty later page with a zero total', async () => {
		mockFetch.mockResolvedValue(pageOf([], 0));
		const list = new DashboardJobs();
		list.page = 2;
		await list.load();
		expect(mockFetch).toHaveBeenCalledTimes(1);
		expect(list.page).toBe(2);
	});

	it('prunes the selection to the visible page', async () => {
		mockFetch.mockResolvedValue(pageOf(['a', 'b']));
		const list = new DashboardJobs();
		list.selected.add('a');
		list.selected.add('gone');
		await list.load();
		expect([...list.selected]).toEqual(['a']);
	});

	it('setStatusFilter resets the page and selection and reloads', async () => {
		mockFetch.mockResolvedValue(pageOf(['a']));
		const list = new DashboardJobs();
		list.page = 3;
		list.selected.add('a');
		list.setStatusFilter('failed');
		expect(list.statusFilter).toBe('failed');
		expect(list.page).toBe(1);
		expect(list.selected.size).toBe(0);
		expect(mockFetch).toHaveBeenCalledWith({ status: 'failed', limit: 48, offset: 0 });
		await vi.waitFor(() => expect(list.loading).toBe(false));
	});

	it('setPage moves the page, clears the selection and reloads', async () => {
		mockFetch.mockResolvedValue(pageOf(['a'], 100));
		const list = new DashboardJobs();
		list.selected.add('a');
		list.setPage(2);
		expect(list.page).toBe(2);
		expect(list.selected.size).toBe(0);
		expect(mockFetch).toHaveBeenCalledWith({ status: undefined, limit: 48, offset: 48 });
		await vi.waitFor(() => expect(list.loading).toBe(false));
	});

	it('toggleSelect adds and removes a job', () => {
		const list = new DashboardJobs();
		list.toggleSelect('a', true);
		expect(list.selected.has('a')).toBe(true);
		list.toggleSelect('a', false);
		expect(list.selected.has('a')).toBe(false);
	});

	it('toggleSelectAll does nothing before any jobs load', () => {
		const list = new DashboardJobs();
		list.selected.add('x');
		list.toggleSelectAll();
		expect([...list.selected]).toEqual(['x']);
	});

	it('toggleSelectAll selects every visible job, then clears them', async () => {
		mockFetch.mockResolvedValue(pageOf(['a', 'b']));
		const list = new DashboardJobs();
		await list.load();
		list.toggleSelectAll();
		expect([...list.selected].sort()).toEqual(['a', 'b']);
		expect(list.allVisibleSelected).toBe(true);
		list.toggleSelectAll();
		expect(list.selected.size).toBe(0);
		expect(list.allVisibleSelected).toBe(false);
	});

	it('allVisibleSelected is false for a partial selection or an empty page', async () => {
		mockFetch.mockResolvedValue(pageOf(['a', 'b']));
		const list = new DashboardJobs();
		await list.load();
		list.selected.add('a');
		expect(list.allVisibleSelected).toBe(false);
		mockFetch.mockResolvedValue(pageOf([], 0));
		await list.load();
		expect(list.allVisibleSelected).toBe(false);
	});
});
