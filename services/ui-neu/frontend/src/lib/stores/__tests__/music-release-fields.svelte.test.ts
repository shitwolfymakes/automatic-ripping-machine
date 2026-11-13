import { describe, it, expect } from 'vitest';
import { flushSync } from 'svelte';
import { MusicReleaseFields } from '$lib/stores/music-release-fields.svelte';
import type { JobView, MetadataReleaseDetail } from '$lib/types/api.gen';

function job(over: Record<string, unknown> = {}): JobView {
	return { disc_number: null, disc_total: null, ...over } as unknown as JobView;
}

function release(over: Record<string, unknown> = {}): MetadataReleaseDetail {
	return {
		title: 'Album',
		artist: 'Artist',
		year: 1999,
		disc_count: null,
		...over
	} as unknown as MetadataReleaseDetail;
}

describe('MusicReleaseFields constructor', () => {
	it('starts with blank fields when the job has no disc numbers', () => {
		const f = new MusicReleaseFields(job());
		expect([f.album, f.artist, f.year, f.discNumber, f.discTotal]).toEqual(['', '', '', '', '']);
	});

	it('seeds the disc fields from the job numbers', () => {
		const f = new MusicReleaseFields(job({ disc_number: 2, disc_total: 3 }));
		expect(f.discNumber).toBe('2');
		expect(f.discTotal).toBe('3');
		expect(f.album).toBe('');
	});
});

describe('MusicReleaseFields.seed', () => {
	it('sets album, artist and year from the release', () => {
		const f = new MusicReleaseFields(job());
		f.seed(release());
		expect([f.album, f.artist, f.year]).toEqual(['Album', 'Artist', '1999']);
	});

	it('sets artist and year to blank when the release has none', () => {
		const f = new MusicReleaseFields(job());
		f.seed(release({ artist: null, year: null }));
		expect([f.album, f.artist, f.year]).toEqual(['Album', '', '']);
	});

	it('fills a blank disc total from a multi-disc release', () => {
		const f = new MusicReleaseFields(job());
		f.seed(release({ disc_count: 4 }));
		expect(f.discTotal).toBe('4');
	});

	it('leaves a set disc total on a multi-disc release', () => {
		const f = new MusicReleaseFields(job({ disc_total: 2 }));
		f.seed(release({ disc_count: 4 }));
		expect(f.discTotal).toBe('2');
	});

	it('leaves a blank disc total blank on a single-disc release', () => {
		const f = new MusicReleaseFields(job());
		f.seed(release({ disc_count: 1 }));
		expect(f.discTotal).toBe('');
	});

	it('leaves a blank disc total blank when disc_count is null', () => {
		const f = new MusicReleaseFields(job());
		f.seed(release({ disc_count: null }));
		expect(f.discTotal).toBe('');
	});

	it('leaves the disc number alone', () => {
		const f = new MusicReleaseFields(job({ disc_number: 2 }));
		f.seed(release({ disc_count: 4 }));
		expect(f.discNumber).toBe('2');
	});
});

describe('MusicReleaseFields.seed inside an effect (#593)', () => {
	function runs(detail: MetadataReleaseDetail): { count: () => number; f: MusicReleaseFields; stop: () => void } {
		const f = new MusicReleaseFields(job());
		let n = 0;
		const stop = $effect.root(() => {
			$effect(() => {
				n++;
				f.seed(detail);
			});
		});
		flushSync();
		return { count: () => n, f, stop };
	}

	it('re-runs when disc total changes for a multi-disc release', () => {
		const { count, f, stop } = runs(release({ disc_count: 3 }));
		// Each blanking re-runs the effect, which refills the total from the
		// release (the fill itself re-runs it once more).
		const settled = count();
		f.discTotal = '';
		flushSync();
		expect(count()).toBeGreaterThan(settled);
		expect(f.discTotal).toBe('3');
		stop();
	});

	it('does not re-run when disc total changes for a single-disc release', () => {
		const { count, f, stop } = runs(release({ disc_count: 1 }));
		f.discTotal = '5';
		flushSync();
		expect(count()).toBe(1);
		stop();
	});
});
