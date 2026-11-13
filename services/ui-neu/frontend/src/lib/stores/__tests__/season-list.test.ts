import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SeasonList } from '../season-list.svelte';

vi.mock('$lib/api/identity', () => ({ fetchSeasons: vi.fn() }));

import { fetchSeasons } from '$lib/api/identity';

type Deferred = { resolve: (v: { seasons?: number[] }) => void; reject: (e: Error) => void };

function pending(): Deferred {
	let d!: Deferred;
	const promise = new Promise((resolve, reject) => {
		d = { resolve: resolve as Deferred['resolve'], reject };
	});
	vi.mocked(fetchSeasons).mockImplementationOnce(() => promise as ReturnType<typeof fetchSeasons>);
	return d;
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('SeasonList', () => {
	beforeEach(() => {
		vi.mocked(fetchSeasons).mockReset();
	});

	it('starts as an empty list', () => {
		expect(new SeasonList().seasons).toEqual([]);
	});

	it('empties the list, fetches, and keeps the response seasons', async () => {
		const list = new SeasonList();
		list.seasons = [9];
		const d = pending();
		list.follow('j1', 'tmdb');
		expect(list.seasons).toEqual([]);
		expect(fetchSeasons).toHaveBeenCalledWith('j1', 'tmdb');
		d.resolve({ seasons: [1, 2] });
		await flush();
		expect(list.seasons).toEqual([1, 2]);
	});

	it('sets [] when the response has no seasons', async () => {
		const list = new SeasonList();
		const d = pending();
		list.follow('j1', 'tmdb');
		d.resolve({});
		await flush();
		expect(list.seasons).toEqual([]);
	});

	it('does not fetch again for the same job and source, loading or loaded', async () => {
		const list = new SeasonList();
		const d = pending();
		list.follow('j1', 'tmdb');
		list.follow('j1', 'tmdb');
		expect(fetchSeasons).toHaveBeenCalledTimes(1);
		d.resolve({ seasons: [1] });
		await flush();
		list.follow('j1', 'tmdb');
		expect(fetchSeasons).toHaveBeenCalledTimes(1);
		expect(list.seasons).toEqual([1]);
	});

	it('ignores a response for a key no longer current', async () => {
		const list = new SeasonList();
		const first = pending();
		list.follow('j1', 'tmdb');
		const second = pending();
		list.follow('j1', 'tvdb');
		first.resolve({ seasons: [1] });
		await flush();
		expect(list.seasons).toEqual([]);
		second.resolve({ seasons: [5] });
		await flush();
		expect(list.seasons).toEqual([5]);
	});

	it('ignores a failure for a key no longer current', async () => {
		const list = new SeasonList();
		const first = pending();
		list.follow('j1', 'tmdb');
		const second = pending();
		list.follow('j1', 'tvdb');
		first.reject(new Error('late'));
		await flush();
		expect(list.seasons).toEqual([]);
		second.resolve({ seasons: [5] });
		await flush();
		expect(list.seasons).toEqual([5]);
	});

	it('sets null on a current failure and fetches again on the next follow', async () => {
		const list = new SeasonList();
		const d = pending();
		list.follow('j1', 'tmdb');
		d.reject(new Error('boom'));
		await flush();
		expect(list.seasons).toBeNull();
		const retry = pending();
		list.follow('j1', 'tmdb');
		expect(fetchSeasons).toHaveBeenCalledTimes(2);
		expect(list.seasons).toEqual([]);
		retry.resolve({ seasons: [3] });
		await flush();
		expect(list.seasons).toEqual([3]);
	});

	it('reset empties the list and lets the old key fetch again', async () => {
		const list = new SeasonList();
		const d = pending();
		list.follow('j1', 'tmdb');
		d.resolve({ seasons: [1] });
		await flush();
		list.reset();
		expect(list.seasons).toEqual([]);
		pending();
		list.follow('j1', 'tmdb');
		expect(fetchSeasons).toHaveBeenCalledTimes(2);
	});
});
