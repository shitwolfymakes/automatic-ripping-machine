import { describe, it, expect } from 'vitest';
import { hintIgnored, withHintIgnored, enabledLabels, previewRows } from '../identity-card';
import { IDENTITY_METAS, IDENTITY_DEFAULTS } from './fixtures/identity-metas';

const v = (over: Record<string, unknown> = {}) => ({ ...IDENTITY_DEFAULTS, ...over });

describe('withHintIgnored', () => {
	it('ignoring label keeps bd_title; un-ignoring restores the default order', () => {
		const ignored = withHintIgnored({ disc_hint_sources: ['bd_title', 'label'] }, 'label', true);
		expect(ignored).toEqual(['bd_title']);
		expect(withHintIgnored({ disc_hint_sources: ignored }, 'label', false)).toEqual(['bd_title', 'label']);
	});

	it('un-ignoring bd_title on [label] puts it first, never after label', () => {
		expect(withHintIgnored({ disc_hint_sources: ['label'] }, 'bd_title', false)).toEqual(['bd_title', 'label']);
	});

	it('ignoring on an empty list stays empty', () => {
		expect(withHintIgnored({ disc_hint_sources: [] }, 'label', true)).toEqual([]);
		expect(withHintIgnored({ disc_hint_sources: [] }, 'bd_title', true)).toEqual([]);
	});

	it('treats a non-array value as the default', () => {
		expect(withHintIgnored({ disc_hint_sources: null }, 'bd_title', true)).toEqual(['label']);
		expect(withHintIgnored({}, 'label', false)).toEqual(['bd_title', 'label']);
	});
});

describe('hintIgnored', () => {
	it('reads absence from disc_hint_sources, a non-array value as the default', () => {
		expect(hintIgnored({ disc_hint_sources: ['bd_title'] }, 'label')).toBe(true);
		expect(hintIgnored({ disc_hint_sources: ['bd_title'] }, 'bd_title')).toBe(false);
		expect(hintIgnored({}, 'label')).toBe(false);
	});
});

describe('enabledLabels', () => {
	it('maps the enabled entries to their enum labels, in order', () => {
		expect(enabledLabels(v({ episode_sources: ['tvdb', 'tmdb'] }), 'episode_sources', IDENTITY_METAS)).toEqual([
			'TVDB',
			'TMDb'
		]);
		expect(enabledLabels(v({ movie_sources: 'x' }), 'movie_sources', IDENTITY_METAS)).toEqual([]);
	});
});

const MOVIES = [
	{ rank: 1, label: 'TMDb' },
	{ rank: 2, label: 'OMDb' }
];
const TV = [
	{ rank: 1, label: 'TMDb' },
	{ rank: 2, label: 'TVmaze' },
	{ rank: 3, label: 'TVDB' }
];
const TRUSTED = 'Applies confident matches';

describe('previewRows with the defaults', () => {
	it('Blu-ray', () => {
		expect(previewRows('bluray', v(), IDENTITY_METAS)).toEqual([
			{ key: 'disc', label: 'Disc', sentence: 'Disc title metadata and volume label, then TheDiscDB' },
			{ key: 'movie', label: 'Movies', sources: MOVIES, trust: TRUSTED },
			{ key: 'tv', label: 'TV shows', sources: TV, trust: TRUSTED }
		]);
	});

	it('DVD with CRC64 on names both databases', () => {
		const rows = previewRows('dvd', v(), IDENTITY_METAS);
		expect(rows.map((r) => r.key)).toEqual(['disc', 'movie', 'tv']);
		expect(rows[0].sentence).toBe('Volume label, then TheDiscDB and the ARM community database');
	});

	it('CD has a disc row and a single music row', () => {
		expect(previewRows('cd', v(), IDENTITY_METAS)).toEqual([
			{ key: 'disc', label: 'Disc', sentence: 'Volume label and disc ID (track layout)' },
			{ key: 'music', label: 'Music', sources: [{ rank: 1, label: 'MusicBrainz' }], trust: TRUSTED }
		]);
	});
});

describe('previewRows states', () => {
	const disc = (kind: 'bluray' | 'dvd' | 'cd', over: Record<string, unknown>) =>
		previewRows(kind, v(over), IDENTITY_METAS)[0].sentence;

	it('both databases off leaves the volume label alone; one off drops only that one', () => {
		expect(disc('dvd', { thediscdb_enabled: false, crc64service_enabled: false })).toBe('Volume label');
		expect(disc('dvd', { thediscdb_enabled: false })).toBe('Volume label, then the ARM community database');
		expect(disc('bluray', { thediscdb_enabled: false })).toBe('Disc title metadata and volume label');
	});

	it('an ignored hint drops out of the Disc sentence', () => {
		expect(disc('bluray', { disc_hint_sources: ['label'] })).toBe('Volume label, then TheDiscDB');
		expect(disc('bluray', { disc_hint_sources: ['bd_title'] })).toBe('Disc title metadata, then TheDiscDB');
		expect(disc('cd', { disc_hint_sources: ['bd_title'] })).toBe('Disc ID (track layout)');
	});

	it('no hint left reads Disc text ignored', () => {
		expect(disc('bluray', { disc_hint_sources: [] })).toBe('Disc text ignored');
		expect(disc('dvd', { disc_hint_sources: ['bd_title'] })).toBe('Disc text ignored');
	});

	it('an empty list has no pills and reads No sources on', () => {
		const movie = previewRows('bluray', v({ movie_sources: [] }), IDENTITY_METAS)[1];
		expect(movie).toEqual({ key: 'movie', label: 'Movies', sources: [], empty: 'No sources on', trust: TRUSTED });
	});

	it('an auto-apply switch off reads Waits for review', () => {
		const rows = previewRows('bluray', v({ movie_auto_apply: false }), IDENTITY_METAS);
		expect(rows[1].trust).toBe('Waits for review');
		expect(rows[2].trust).toBe(TRUSTED);
		expect(previewRows('cd', v({ music_auto_apply: false }), IDENTITY_METAS)[1].trust).toBe('Waits for review');
	});
});
