import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchMusicDetailMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	fetchMusicDetail: (...a: unknown[]) => fetchMusicDetailMock(...a)
}));

import { MusicFlipCards } from '$lib/stores/music-flip-cards.svelte';
import type { MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';

function candidate(over: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { provider_id: 'r1', title: 'Album', ...over } as MetadataCandidate;
}

function detailOf(id: string): MetadataReleaseDetail {
	return { release_id: id, title: 'Fetched', tracks: [] } as unknown as MetadataReleaseDetail;
}

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
	fetchMusicDetailMock.mockReset();
});

describe('MusicFlipCards', () => {
	it('starts with nothing flipped', () => {
		const f = new MusicFlipCards();
		expect(f.isFlipped('r1')).toBe(false);
		expect(f.get('r1')).toBeUndefined();
	});

	it('toggle on a candidate without provider_id does not fetch or flip', async () => {
		const f = new MusicFlipCards();
		await f.toggle(candidate({ provider_id: undefined }));
		expect(fetchMusicDetailMock).not.toHaveBeenCalled();
		expect(f.isFlipped('r1')).toBe(false);
	});

	it('toggle flips to loading while the fetch is pending, then holds the detail', async () => {
		const d = deferred<MetadataReleaseDetail>();
		fetchMusicDetailMock.mockReturnValue(d.promise);
		const f = new MusicFlipCards();
		const p = f.toggle(candidate());
		expect(f.isFlipped('r1')).toBe(true);
		expect(f.get('r1')).toBe('loading');
		const detail = detailOf('r1');
		d.resolve(detail);
		await p;
		expect(f.get('r1')).toBe(detail);
		expect(fetchMusicDetailMock).toHaveBeenCalledWith('r1');
	});

	it('toggle stores a fallback built from the candidate when the fetch rejects', async () => {
		fetchMusicDetailMock.mockRejectedValue(new Error('boom'));
		const f = new MusicFlipCards();
		await f.toggle(candidate({ year: 1999, poster_url: 'http://p', track_count: 12 }));
		expect(f.get('r1')).toEqual({
			release_id: 'r1',
			title: 'Album',
			artist: null,
			year: 1999,
			poster_url: 'http://p',
			disc_count: null,
			track_count: 12,
			catalog_number: null,
			barcode: null,
			status: null,
			tracks: []
		});
	});

	it('the fallback uses null for year, poster_url and track_count the candidate lacks', async () => {
		fetchMusicDetailMock.mockRejectedValue(new Error('boom'));
		const f = new MusicFlipCards();
		await f.toggle(candidate());
		expect(f.get('r1')).toMatchObject({ year: null, poster_url: null, track_count: null, tracks: [] });
	});

	it('toggle on a flipped card unflips it without fetching and leaves other cards alone', async () => {
		fetchMusicDetailMock.mockResolvedValue(detailOf('x'));
		const f = new MusicFlipCards();
		await f.toggle(candidate({ provider_id: 'r1' }));
		await f.toggle(candidate({ provider_id: 'r2' }));
		fetchMusicDetailMock.mockClear();
		await f.toggle(candidate({ provider_id: 'r1' }));
		expect(fetchMusicDetailMock).not.toHaveBeenCalled();
		expect(f.isFlipped('r1')).toBe(false);
		expect(f.isFlipped('r2')).toBe(true);
	});

	it('unflipping while the fetch is pending flips the card again once it resolves (#594)', async () => {
		const d = deferred<MetadataReleaseDetail>();
		fetchMusicDetailMock.mockReturnValue(d.promise);
		const f = new MusicFlipCards();
		const p = f.toggle(candidate());
		await f.toggle(candidate());
		expect(f.isFlipped('r1')).toBe(false);
		const detail = detailOf('r1');
		d.resolve(detail);
		await p;
		expect(f.isFlipped('r1')).toBe(true);
		expect(f.get('r1')).toBe(detail);
	});

	it('clear unflips every card', async () => {
		fetchMusicDetailMock.mockResolvedValue(detailOf('x'));
		const f = new MusicFlipCards();
		await f.toggle(candidate({ provider_id: 'r1' }));
		await f.toggle(candidate({ provider_id: 'r2' }));
		f.clear();
		expect(f.isFlipped('r1')).toBe(false);
		expect(f.isFlipped('r2')).toBe(false);
	});
});
