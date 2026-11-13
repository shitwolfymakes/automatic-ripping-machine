import { describe, it, expect, vi, afterEach } from 'vitest';
import type { MetadataCandidate } from '$lib/types/api.gen';
import { MatchDetailsCache } from '../../match/match-details.svelte';

vi.mock('$lib/api/jobs', () => ({ fetchMatchDetails: vi.fn() }));
import { fetchMatchDetails } from '$lib/api/jobs';
const mockDetails = vi.mocked(fetchMatchDetails);

const tvRow = {
	title: 'Kolchak: The Night Stalker',
	year: 1974,
	kind: 'tv',
	provider: 'tvmaze',
	external_ids: { tvmaze: '1' },
	facts: null
} as MetadataCandidate;
const movieRow = {
	title: 'The Night Stalker',
	year: 1972,
	kind: 'movie',
	provider: 'tmdb',
	external_ids: { tmdb: '9' },
	facts: null
} as MetadataCandidate;
const seriesRow = { ...tvRow, kind: 'series' } as MetadataCandidate;
const detail = (cast: string[]) => ({
	candidates: [{ title: 'Kolchak', kind: 'tv', provider: 'tvmaze', facts: { cast, genres: [], creators: [] } }]
});
const KEY = 'tvmaze:1';

/** A fetch the test settles itself, to act while the load is in flight. */
function pending() {
	let resolve!: (v: Awaited<ReturnType<typeof fetchMatchDetails>>) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<Awaited<ReturnType<typeof fetchMatchDetails>>>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('MatchDetailsCache.load', () => {
	afterEach(() => {
		vi.clearAllMocks();
	});

	it('resolves to null and fetches nothing for a row with no provider', async () => {
		const cache = new MatchDetailsCache();
		expect(await cache.load({ ...tvRow, provider: null } as MetadataCandidate)).toBeNull();
		expect(mockDetails).not.toHaveBeenCalled();
	});

	it('resolves to null and fetches nothing for a row with no provider id', async () => {
		const cache = new MatchDetailsCache();
		expect(await cache.load({ ...tvRow, external_ids: {} } as MetadataCandidate)).toBeNull();
		expect(mockDetails).not.toHaveBeenCalled();
	});

	it('stores and returns the details found, and clears loading', async () => {
		mockDetails.mockResolvedValue(detail(['A']) as never);
		const cache = new MatchDetailsCache();
		const found = await cache.load(tvRow);
		expect(found).toEqual(detail(['A']).candidates[0]);
		expect(cache.details[KEY]).toEqual(found);
		expect(cache.loading[KEY]).toBe(false);
		expect(cache.errors[KEY]).toBeUndefined();
	});

	it('does not fetch details it already has', async () => {
		mockDetails.mockResolvedValue(detail(['A']) as never);
		const cache = new MatchDetailsCache();
		await cache.load(tvRow);
		expect(await cache.load(tvRow)).toBeNull();
		expect(mockDetails).toHaveBeenCalledTimes(1);
	});

	it('does not fetch a row whose load is in flight', async () => {
		const call = pending();
		mockDetails.mockReturnValue(call.promise);
		const cache = new MatchDetailsCache();
		const first = cache.load(tvRow);
		expect(cache.loading[KEY]).toBe(true);
		expect(await cache.load(tvRow)).toBeNull();
		expect(mockDetails).toHaveBeenCalledTimes(1);
		call.resolve(detail(['A']) as never);
		await first;
	});

	it('asks for tv for a tv row and a series row, movie for a movie row', async () => {
		mockDetails.mockResolvedValue(detail(['A']) as never);
		const cache = new MatchDetailsCache();
		await cache.load(tvRow);
		await cache.load({ ...seriesRow, external_ids: { tvmaze: '2' } } as MetadataCandidate);
		await cache.load(movieRow);
		expect(mockDetails).toHaveBeenNthCalledWith(1, 'tvmaze', 'tv', '1');
		expect(mockDetails).toHaveBeenNthCalledWith(2, 'tvmaze', 'tv', '2');
		expect(mockDetails).toHaveBeenNthCalledWith(3, 'tmdb', 'movie', '9');
	});

	it('stores the response detail when no candidates came', async () => {
		mockDetails.mockResolvedValue({ candidates: [], detail: 'Provider is down' } as never);
		const cache = new MatchDetailsCache();
		expect(await cache.load(tvRow)).toBeNull();
		expect(cache.errors[KEY]).toBe('Provider is down');
		expect(cache.loading[KEY]).toBe(false);
	});

	it('stores "No details found." when no candidates came and no detail', async () => {
		mockDetails.mockResolvedValue({ candidates: [] } as never);
		const cache = new MatchDetailsCache();
		await cache.load(tvRow);
		expect(cache.errors[KEY]).toBe('No details found.');
	});

	it('stores the message of an Error the fetch rejects with', async () => {
		mockDetails.mockRejectedValue(new Error('boom'));
		const cache = new MatchDetailsCache();
		expect(await cache.load(tvRow)).toBeNull();
		expect(cache.errors[KEY]).toBe('boom');
		expect(cache.loading[KEY]).toBe(false);
	});

	it('stores "Could not load details" when the fetch rejects with a non-Error', async () => {
		mockDetails.mockRejectedValue('nope');
		const cache = new MatchDetailsCache();
		await cache.load(tvRow);
		expect(cache.errors[KEY]).toBe('Could not load details');
	});

	it('replaces an old error with a new one, and a retry clears it first', async () => {
		const cache = new MatchDetailsCache();
		mockDetails.mockRejectedValueOnce(new Error('first'));
		await cache.load(tvRow);
		expect(cache.errors[KEY]).toBe('first');

		const call = pending();
		mockDetails.mockReturnValueOnce(call.promise);
		const retry = cache.load(tvRow);
		expect(cache.errors[KEY]).toBeUndefined();
		call.reject(new Error('second'));
		await retry;
		expect(cache.errors[KEY]).toBe('second');
	});

	it('writes nothing and resolves to null when reset while its fetch resolves', async () => {
		const call = pending();
		mockDetails.mockReturnValue(call.promise);
		const cache = new MatchDetailsCache();
		const load = cache.load(tvRow);
		cache.reset();
		call.resolve(detail(['A']) as never);
		expect(await load).toBeNull();
		expect(cache.details).toEqual({});
		expect(cache.errors).toEqual({});
		expect(cache.loading).toEqual({});
	});

	it('writes nothing and resolves to null when reset while its fetch rejects', async () => {
		const call = pending();
		mockDetails.mockReturnValue(call.promise);
		const cache = new MatchDetailsCache();
		const load = cache.load(tvRow);
		cache.reset();
		call.reject(new Error('late'));
		expect(await load).toBeNull();
		expect(cache.details).toEqual({});
		expect(cache.errors).toEqual({});
		expect(cache.loading).toEqual({});
	});
});

describe('MatchDetailsCache.merged', () => {
	afterEach(() => {
		vi.clearAllMocks();
	});

	it('is the row alone before its details load, the merged row after', async () => {
		mockDetails.mockResolvedValue(detail(['A']) as never);
		const cache = new MatchDetailsCache();
		expect(cache.merged(tvRow)).toBe(tvRow);
		await cache.load(tvRow);
		const merged = cache.merged(tvRow);
		expect(merged).not.toBe(tvRow);
		expect(merged.facts?.cast).toEqual(['A']);
		expect(merged.year).toBe(1974);
	});
});
