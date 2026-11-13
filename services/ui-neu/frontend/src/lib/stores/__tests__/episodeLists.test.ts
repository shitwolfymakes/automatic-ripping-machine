import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { EpisodeSummary } from '$lib/types/api.gen';

vi.mock('$lib/api/identity', () => ({ fetchEpisodes: vi.fn() }));

import { fetchEpisodes } from '$lib/api/identity';
import { EpisodeLists } from '../episode-lists.svelte';

const mockFetch = vi.mocked(fetchEpisodes);

const ep = (n: number) => ({ episode_number: n }) as unknown as EpisodeSummary;
const reply = (...eps: EpisodeSummary[]) => ({ episodes: eps }) as Awaited<ReturnType<typeof fetchEpisodes>>;
const flush = () => new Promise((r) => setTimeout(r, 0));

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
	mockFetch.mockResolvedValue(reply());
});

describe('EpisodeLists', () => {
	it('gives [] for a season with no list', () => {
		expect(new EpisodeLists().get(1)).toEqual([]);
	});

	it('fetches each season once and fills get from the response', async () => {
		mockFetch.mockImplementation(async (_j, _s, season) => reply(ep(season * 10)));
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1, 2]);
		await flush();
		expect(mockFetch).toHaveBeenCalledTimes(2);
		expect(lists.get(1)).toEqual([ep(10)]);
		expect(lists.get(2)).toEqual([ep(20)]);
	});

	it('gives [] for a response with no episodes', async () => {
		mockFetch.mockResolvedValue({} as Awaited<ReturnType<typeof fetchEpisodes>>);
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		await flush();
		expect(lists.get(1)).toEqual([]);
	});

	it('does not fetch a season already asked for, loading or loaded', async () => {
		const d = deferred<ReturnType<typeof reply>>();
		mockFetch.mockReturnValue(d.promise);
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		lists.want('j1', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(1);
		d.resolve(reply(ep(1)));
		await flush();
		lists.want('j1', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(1);
	});

	it('drops the lists and fetches again for a new job or a new source', async () => {
		mockFetch.mockResolvedValue(reply(ep(1)));
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		await flush();
		lists.want('j2', 'tmdb' as never, [1]);
		expect(lists.get(1)).toEqual([]);
		await flush();
		lists.want('j2', 'tvdb' as never, [1]);
		expect(lists.get(1)).toEqual([]);
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it('ignores a response that arrives after the key changed', async () => {
		const d = deferred<ReturnType<typeof reply>>();
		mockFetch.mockReturnValueOnce(d.promise);
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		lists.want('j2', 'tmdb' as never, []);
		d.resolve(reply(ep(1)));
		await flush();
		expect(lists.get(1)).toEqual([]);
	});

	it('asks again for a season whose fetch failed for the current key', async () => {
		mockFetch.mockRejectedValueOnce(new Error('x'));
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		await flush();
		lists.want('j1', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('leaves the new key alone when a failure arrives after the key changed', async () => {
		const d = deferred<ReturnType<typeof reply>>();
		mockFetch.mockReturnValueOnce(d.promise);
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		lists.want('j2', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(2);
		d.reject(new Error('late'));
		await flush();
		lists.want('j2', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('drops the lists on reset and fetches again on the next want', async () => {
		mockFetch.mockResolvedValue(reply(ep(1)));
		const lists = new EpisodeLists();
		lists.want('j1', 'tmdb' as never, [1]);
		await flush();
		lists.reset();
		expect(lists.get(1)).toEqual([]);
		lists.want('j1', 'tmdb' as never, [1]);
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});
});
