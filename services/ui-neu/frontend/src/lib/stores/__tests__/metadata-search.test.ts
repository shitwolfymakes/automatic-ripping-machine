import { describe, it, expect, vi } from 'vitest';
import type { MetadataCandidate } from '$lib/types/api.gen';
import { IMDB_LOOKUP, MetadataSearch, type SearchMessages } from '../metadata-search.svelte';

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
		const pending = s.run(
			() => new Promise((r) => (resolve = r)),
			MESSAGES,
			() => {}
		);
		expect(s.searching).toBe(true);
		resolve({ candidates: [candidate('a')] });
		await pending;
		expect(s.searching).toBe(false);
	});

	it('clears the previous error when a run starts', async () => {
		const s = new MetadataSearch();
		s.error = 'old';
		let resolve!: (v: { candidates: MetadataCandidate[] }) => void;
		const pending = s.run(
			() => new Promise((r) => (resolve = r)),
			MESSAGES,
			() => {}
		);
		expect(s.error).toBeNull();
		resolve({ candidates: [candidate('a')] });
		await pending;
	});

	it('hands the candidates to onfound once and leaves no error', async () => {
		const s = new MetadataSearch();
		const found = [candidate('a'), candidate('b')];
		const onfound = vi.fn();
		await s.run(async () => ({ candidates: found }), MESSAGES, onfound);
		expect(onfound).toHaveBeenCalledTimes(1);
		expect(onfound).toHaveBeenCalledWith(found);
		expect(s.error).toBeNull();
	});

	it('hands an empty list to onfound before setting the empty line', async () => {
		const s = new MetadataSearch();
		let errorAtFound: string | null | undefined;
		const onfound = vi.fn(() => (errorAtFound = s.error));
		await s.run(async () => ({ candidates: [] }), MESSAGES, onfound);
		expect(onfound).toHaveBeenCalledTimes(1);
		expect(onfound).toHaveBeenCalledWith([]);
		expect(errorAtFound).toBeNull();
		expect(s.error).toBe('nothing');
		expect(s.searching).toBe(false);
	});

	it('shows an Error message and skips onfound when the request rejects', async () => {
		const s = new MetadataSearch();
		const onfound = vi.fn();
		await s.run(() => Promise.reject(new Error('boom')), MESSAGES, onfound);
		expect(onfound).not.toHaveBeenCalled();
		expect(s.error).toBe('boom');
		expect(s.searching).toBe(false);
	});

	it('shows the failed line when the rejection is not an Error', async () => {
		const s = new MetadataSearch();
		const onfound = vi.fn();
		await s.run(() => Promise.reject('nope'), MESSAGES, onfound);
		expect(onfound).not.toHaveBeenCalled();
		expect(s.error).toBe('broke');
		expect(s.searching).toBe(false);
	});
});

describe('IMDB_LOOKUP', () => {
	it('carries the IMDb lookup lines', () => {
		expect(IMDB_LOOKUP).toEqual({ empty: 'No match found for that IMDb ID.', failed: 'IMDb lookup failed' });
	});
});
