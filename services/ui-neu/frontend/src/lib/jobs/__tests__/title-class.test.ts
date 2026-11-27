import { describe, it, expect } from 'vitest';
import {
	DECOY_GROUP_MIN,
	decoyGroupText,
	groupDecoys,
	isDecoyGroup,
	isRawStream,
	refIndexOf,
	refText,
	sourceName,
	titleClassLabel
} from '../title-class';
import type { TitleClass } from '$lib/types/api.gen';

const idx = (ref: string) => (ref === '0' ? 0 : null);

describe('refIndexOf / refText', () => {
	it('maps a source_ref to the row number, else null', () => {
		const lookup = refIndexOf([{ source_ref: 'a', index: 7 }]);
		expect(lookup('a')).toBe(7);
		expect(lookup('zz')).toBeNull();
	});
	it('names the row, the raw ref, or an unknown title', () => {
		expect(refText('0', idx)).toBe('#0');
		expect(refText('9', idx)).toBe('title 9');
		expect(refText(null, idx)).toBe('another title');
		expect(refText(undefined, idx)).toBe('another title');
	});
});

describe('isRawStream', () => {
	it.each([
		[{ source_file: '00294.m2ts', playlist_name: null }, true],
		[{ source_file: '00294.M2TS' }, true],
		[{ source_file: '00294.m2ts', playlist_name: '00801.mpls' }, false],
		[{ source_file: '00801.mpls' }, false],
		[{ source_file: null }, false],
		[{}, false]
	])('%j -> %s', (t, want) => {
		expect(isRawStream(t)).toBe(want);
	});
});

describe('titleClassLabel', () => {
	const label = (o: object) => titleClassLabel(o as never, idx);
	it('has no label for a primary, a missing class or an unknown one', () => {
		expect(label({ title_class: 'primary' })).toBeNull();
		expect(label({ title_class: null })).toBeNull();
		expect(label({})).toBeNull();
	});
	it('labels an edition with its length, else bare', () => {
		expect(label({ title_class: 'edition', duration_seconds: 8020 })).toEqual({
			text: 'Edition (2h 13m 40s)',
			tone: 'info'
		});
		expect(label({ title_class: 'edition', expected_duration_seconds: 60 })).toEqual({
			text: 'Edition (1m 0s)',
			tone: 'info'
		});
		expect(label({ title_class: 'edition' })).toEqual({ text: 'Edition', tone: 'info' });
	});
	it('labels a copy, telling a stream file from a playlist', () => {
		expect(label({ title_class: 'duplicate', title_class_ref: '0', source_file: '1.m2ts' })).toEqual({
			text: 'Copy of #0 (stream file)',
			tone: 'muted'
		});
		expect(label({ title_class: 'duplicate', title_class_ref: '0', playlist_name: '2.mpls' })).toEqual({
			text: 'Copy of #0',
			tone: 'muted'
		});
	});
	it('labels a decoy and a variant, falling back for an unknown ref', () => {
		expect(label({ title_class: 'decoy', title_class_ref: '0' })?.text).toBe('Decoy playlist of #0');
		expect(label({ title_class: 'variant', title_class_ref: '0' })?.text).toBe('#0 with an extra intro');
		expect(label({ title_class: 'decoy', title_class_ref: '5' })?.text).toBe('Decoy playlist of title 5');
	});
});

describe('sourceName', () => {
	it('prefers the ripped file, then the playlist, the stream file, the ref', () => {
		const all = { output_path: 'o.mkv', playlist_name: 'p.mpls', source_file: 's.m2ts', source_ref: '3' };
		expect(sourceName(all)).toBe('o.mkv');
		expect(sourceName({ ...all, output_path: '' })).toBe('p.mpls');
		expect(sourceName({ ...all, output_path: null, playlist_name: null })).toBe('s.m2ts');
		expect(sourceName({ output_path: null, playlist_name: null, source_file: null, source_ref: '3' })).toBe('3');
	});
});

describe('decoyGroupText', () => {
	it('says unticked, or how many are ticked, and pluralises', () => {
		expect(decoyGroupText(298, 0, '#0')).toBe('298 decoy playlists of #0 (unticked)');
		expect(decoyGroupText(3, 2, '#0')).toBe('3 decoy playlists of #0 (2 ticked)');
		expect(decoyGroupText(1, 0, '#0')).toBe('1 decoy playlist of #0 (unticked)');
	});
});

describe('groupDecoys', () => {
	const row = (n: number, titleClass: TitleClass | null, classRef: string | null = null) => ({
		n,
		titleClass,
		classRef,
		sourceRef: String(n)
	});
	it('exports a threshold of 3', () => {
		expect(DECOY_GROUP_MIN).toBe(3);
	});
	it('leaves rows alone below the threshold', () => {
		const rows = [row(0, 'primary'), row(1, 'decoy', '0'), row(2, 'decoy', '0')];
		expect(groupDecoys(rows, 3)).toEqual(rows);
	});
	it('collapses at the threshold into one group right after the title it copies', () => {
		const rows = [
			row(0, 'primary'),
			row(1, 'decoy', '0'),
			row(2, 'edition'),
			row(3, 'decoy', '0'),
			row(4, 'decoy', '0')
		];
		const out = groupDecoys(rows, 3);
		expect(out).toHaveLength(3);
		expect(out[0]).toBe(rows[0]);
		expect(isDecoyGroup(out[1])).toBe(true);
		expect(out[1]).toMatchObject({ ref: '0', members: [rows[1], rows[3], rows[4]] });
		expect(out[2]).toBe(rows[2]);
		expect(isDecoyGroup(out[0])).toBe(false);
	});
	it('puts a group last when the title it copies is not a row, and keeps groups per ref', () => {
		const rows = [
			row(1, 'decoy', '9'),
			row(2, 'decoy', '9'),
			row(3, 'decoy', '9'),
			row(4, 'primary'),
			row(5, 'decoy', null)
		];
		const out = groupDecoys(rows, 3);
		expect(out.map((o) => (isDecoyGroup(o) ? `g${o.ref}` : o.n))).toEqual([4, 5, 'g9']);
	});
});
