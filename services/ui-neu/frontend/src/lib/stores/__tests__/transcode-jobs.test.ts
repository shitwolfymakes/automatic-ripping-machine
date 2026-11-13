import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { TranscodeTaskView } from '$lib/types/api.gen';

const fetchJobsMock = vi.fn();
vi.mock('$lib/api/transcoder', () => ({
	fetchTranscoderJobs: (...a: unknown[]) => fetchJobsMock(...a),
	fetchTranscoderStats: vi.fn(),
	fetchTranscoderWorkers: vi.fn()
}));

// The per-tab cache is module state in $lib/stores/transcoder, so each test
// resets the module registry and imports the class and the cache afresh.
async function load(seed?: { tab: string; data: TranscodeTaskView[] }) {
	vi.resetModules();
	const cache = await import('$lib/stores/transcoder');
	if (seed) cache.setJobsCache(seed.tab, seed.data);
	const { TranscodeJobs } = await import('$lib/stores/transcode-jobs.svelte');
	return { jobs: new TranscodeJobs(), cache };
}

const task = (id: string, status: string, created_at: string) =>
	({ id, status, created_at }) as unknown as TranscodeTaskView;
const OLD = task('old', 'done', '2026-01-01T00:00:00Z');
const NEW = task('new', 'done', '2026-02-01T00:00:00Z');
const ACTIVE = task('active', 'in_progress', '2025-01-01T00:00:00Z');

beforeEach(() => {
	vi.useFakeTimers();
	fetchJobsMock.mockReset();
	fetchJobsMock.mockResolvedValue([]);
});

afterEach(() => {
	vi.useRealTimers();
});

describe('TranscodeJobs first state', () => {
	it('starts empty and loading on the all tab with nothing cached', async () => {
		const { jobs } = await load();
		expect(jobs.activeTab).toBe('all');
		expect(jobs.jobs).toEqual([]);
		expect(jobs.sorted).toEqual([]);
		expect(jobs.loading).toBe(true);
		expect(jobs.error).toBeNull();
	});

	it('starts from the cached all list, not loading', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		expect(jobs.jobs).toEqual([OLD]);
		expect(jobs.loading).toBe(false);
	});
});

describe('TranscodeJobs.load', () => {
	it('loads the jobs, caches them under the tab and sorts them', async () => {
		fetchJobsMock.mockResolvedValue([OLD, NEW, ACTIVE]);
		const { jobs, cache } = await load();
		await jobs.load();
		expect(jobs.jobs).toEqual([OLD, NEW, ACTIVE]);
		expect(jobs.sorted).toEqual([ACTIVE, NEW, OLD]);
		expect(cache.getJobsCache('all')).toEqual([OLD, NEW, ACTIVE]);
		expect(jobs.loading).toBe(false);
		expect(jobs.error).toBeNull();
	});

	it('raises the loading flag while loading when asked to', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		let resolve!: (v: TranscodeTaskView[]) => void;
		fetchJobsMock.mockReturnValue(new Promise((r) => (resolve = r)));
		const pending = jobs.load();
		expect(jobs.loading).toBe(true);
		resolve([NEW]);
		await pending;
		expect(jobs.loading).toBe(false);
	});

	it('leaves the loading flag down for a background load', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		let resolve!: (v: TranscodeTaskView[]) => void;
		fetchJobsMock.mockReturnValue(new Promise((r) => (resolve = r)));
		const pending = jobs.load(false);
		expect(jobs.loading).toBe(false);
		resolve([NEW]);
		await pending;
		expect(jobs.jobs).toEqual([NEW]);
	});

	it('keeps the Error and empties the jobs when the load fails', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		const err = new Error('boom');
		fetchJobsMock.mockRejectedValue(err);
		await jobs.load();
		expect(jobs.error).toBe(err);
		expect(jobs.jobs).toEqual([]);
		expect(jobs.loading).toBe(false);
	});

	it('wraps a non-Error failure as Failed to load jobs', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		fetchJobsMock.mockRejectedValue('nope');
		await jobs.load();
		expect(jobs.error).toEqual(new Error('Failed to load jobs'));
		expect(jobs.jobs).toEqual([]);
	});

	it('clears the previous error when it starts', async () => {
		const { jobs } = await load();
		fetchJobsMock.mockRejectedValueOnce(new Error('boom'));
		await jobs.load();
		await jobs.load();
		expect(jobs.error).toBeNull();
	});

	it.each([
		['all', undefined],
		['queued', 'queued'],
		['in_progress', 'in_progress'],
		['done', 'done'],
		['failed', 'failed']
	])('sends the %s tab as status %s', async (tab, status) => {
		const { jobs } = await load();
		jobs.activeTab = tab;
		await jobs.load();
		expect(fetchJobsMock).toHaveBeenCalledWith({ status });
	});
});

describe('TranscodeJobs.switchTab', () => {
	it('shows loading on the first visit to a tab', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		fetchJobsMock.mockReturnValue(new Promise(() => {}));
		jobs.switchTab('failed');
		expect(jobs.activeTab).toBe('failed');
		expect(jobs.loading).toBe(true);
		expect(fetchJobsMock).toHaveBeenCalledWith({ status: 'failed' });
	});

	it('does not show loading on a cached tab', async () => {
		const { jobs, cache } = await load({ tab: 'all', data: [OLD] });
		cache.setJobsCache('queued', [OLD]);
		fetchJobsMock.mockReturnValue(new Promise(() => {}));
		jobs.switchTab('queued');
		expect(jobs.loading).toBe(false);
		expect(fetchJobsMock).toHaveBeenCalledWith({ status: 'queued' });
	});

	it('caches a response that lands after a switch under the new tab', async () => {
		const { jobs, cache } = await load();
		let resolve!: (v: TranscodeTaskView[]) => void;
		fetchJobsMock.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		const pending = jobs.load();
		jobs.switchTab('done');
		resolve([OLD]);
		await pending;
		expect(cache.getJobsCache('done')).toEqual([OLD]);
		expect(cache.getJobsCache('all')).toBeNull();
	});
});

describe('TranscodeJobs polling', () => {
	it('loads every 5 s without the loading flag', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		jobs.startPolling();
		expect(fetchJobsMock).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(5000);
		expect(fetchJobsMock).toHaveBeenCalledTimes(1);
		expect(jobs.loading).toBe(false);
		await vi.advanceTimersByTimeAsync(5000);
		expect(fetchJobsMock).toHaveBeenCalledTimes(2);
	});

	it('replaces the first timer when started twice', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		jobs.startPolling();
		jobs.startPolling();
		await vi.advanceTimersByTimeAsync(5000);
		expect(fetchJobsMock).toHaveBeenCalledTimes(1);
	});

	it('stops loading once stopped', async () => {
		const { jobs } = await load({ tab: 'all', data: [OLD] });
		jobs.startPolling();
		jobs.stopPolling();
		await vi.advanceTimersByTimeAsync(10000);
		expect(fetchJobsMock).not.toHaveBeenCalled();
	});

	it('does nothing when stopped with no timer', async () => {
		const { jobs } = await load();
		expect(() => jobs.stopPolling()).not.toThrow();
	});
});
