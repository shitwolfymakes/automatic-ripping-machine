import { describe, it, expect } from 'vitest';
import type { MetadataCandidate } from '$lib/types/api.gen';
import { IMDB_LOOKUP, MetadataSearch, type SearchMessages } from '../metadataSearch.svelte';

const MESSAGES: SearchMessages = { empty: 'nothing', failed: 'broke' };
const candidate = (title: string) => ({ title }) as unknown as MetadataCandidate;

describe('MetadataSearch', () => {
	it('starts idle with no error', () => {
		const s = new MetadataSearch();
		expect(s.searching).toBe(false);
		expect(s.error).toBeNull();
	});

	it('is searching while the request is pending and not after it resolves', async () => {
		const s = new MetadataSearch();
		let resolve!: (v: { candidates: MetadataCandidate[] }) => void;
		const pending = s.run(() => new Promise((r) => (resolve = r)), MESSAGES);
		expect(s.searching).toBe(true);
		resolve({ candidates: [candidate('a')] });
		await pending;
		expect(s.searching).toBe(false);
	});

	it('clears the previous error when a run starts', async () => {
		const s = new MetadataSearch();
		s.error = 'old';
		let resolve!: (v: { candidates: MetadataCandidate[] }) => void;
		const pending = s.run(() => new Promise((r) => (resolve = r)), MESSAGES);
		expect(s.error).toBeNull();
		resolve({ candidates: [candidate('a')] });
		await pending;
	});

	it('returns the candidates and leaves no error', async () => {
		const s = new MetadataSearch();
		const found = [candidate('a'), candidate('b')];
		expect(await s.run(async () => ({ candidates: found }), MESSAGES)).toEqual(found);
		expect(s.error).toBeNull();
	});

	it('shows the empty line when there are no candidates', async () => {
		const s = new MetadataSearch();
		expect(await s.run(async () => ({ candidates: [] }), MESSAGES)).toEqual([]);
		expect(s.error).toBe('nothing');
		expect(s.searching).toBe(false);
	});

	it('shows an Error message and returns none when the request rejects', async () => {
		const s = new MetadataSearch();
		const out = await s.run(() => Promise.reject(new Error('boom')), MESSAGES);
		expect(out).toEqual([]);
		expect(s.error).toBe('boom');
		expect(s.searching).toBe(false);
	});

	it('shows the failed line when the rejection is not an Error', async () => {
		const s = new MetadataSearch();
		const out = await s.run(() => Promise.reject('nope'), MESSAGES);
		expect(out).toEqual([]);
		expect(s.error).toBe('broke');
		expect(s.searching).toBe(false);
	});
});

describe('IMDB_LOOKUP', () => {
	it('carries the IMDb lookup lines', () => {
		expect(IMDB_LOOKUP).toEqual({ empty: 'No match found for that IMDb ID.', failed: 'IMDb lookup failed' });
	});
});
