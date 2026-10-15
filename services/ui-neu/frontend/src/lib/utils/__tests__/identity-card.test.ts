import { describe, it, expect } from 'vitest';
import { hintIgnored, withHintIgnored, enabledLabels, stripCells } from '../identity-card';
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

describe('stripCells with the defaults', () => {
	it('Blu-ray', () => {
		expect(stripCells('bluray', v(), IDENTITY_METAS)).toEqual([
			{ label: 'On the disc', value: 'Disc title metadata, Volume label', sub: 'ARM reads all of these' },
			{ label: 'Disc database', value: 'TheDiscDB disc map', sub: "A match wins over the disc's labels" },
			{
				label: 'Online lookup',
				value: 'Movies: TMDb, OMDb · TV shows: TMDb, TVmaze, TVDB',
				sub: 'Tried top to bottom; the first confident match wins'
			},
			{
				label: 'Trust',
				value: 'Movies: Apply confident matches · TV shows: Apply confident matches',
				sub: 'Others wait for review on the job page'
			}
		]);
	});

	it('DVD', () => {
		expect(stripCells('dvd', v(), IDENTITY_METAS)).toEqual([
			{ label: 'On the disc', value: 'Volume label', sub: 'ARM reads all of these' },
			{
				label: 'Disc database',
				value: 'TheDiscDB disc map, ARM community database (CRC64)',
				sub: "A match wins over the disc's labels"
			},
			{
				label: 'Online lookup',
				value: 'Movies: TMDb, OMDb · TV shows: TMDb, TVmaze, TVDB',
				sub: 'Tried top to bottom; the first confident match wins'
			},
			{
				label: 'Trust',
				value: 'Movies: Apply confident matches · TV shows: Apply confident matches',
				sub: 'Others wait for review on the job page'
			}
		]);
	});

	it('CD', () => {
		expect(stripCells('cd', v(), IDENTITY_METAS)).toEqual([
			{ label: 'On the disc', value: 'Volume label, Disc ID (track layout)', sub: 'CD-TEXT planned' },
			{ label: 'Disc database', value: 'Not used for CDs' },
			{
				label: 'Online lookup',
				value: 'Music: MusicBrainz',
				sub: 'Tried top to bottom; the first confident match wins'
			},
			{ label: 'Trust', value: 'Music: Apply confident matches', sub: 'Others wait for review on the job page' }
		]);
	});
});

describe('stripCells states', () => {
	it('an empty episode list reads No sources on', () => {
		expect(stripCells('bluray', v({ episode_sources: [] }), IDENTITY_METAS)[2].value).toBe(
			'Movies: TMDb, OMDb · TV shows: No sources on'
		);
		expect(stripCells('cd', v({ music_sources: [] }), IDENTITY_METAS)[2].value).toBe('Music: No sources on');
	});

	it('both disc databases off reads Off', () => {
		const cells = stripCells('dvd', v({ thediscdb_enabled: false, crc64service_enabled: false }), IDENTITY_METAS);
		expect(cells[1].value).toBe('Off');
		expect(stripCells('bluray', v({ thediscdb_enabled: false }), IDENTITY_METAS)[1].value).toBe('Off');
		expect(stripCells('dvd', v({ thediscdb_enabled: false }), IDENTITY_METAS)[1].value).toBe(
			'ARM community database (CRC64)'
		);
	});

	it('every hint ignored reads Disc text ignored / See Advanced', () => {
		expect(stripCells('bluray', v({ disc_hint_sources: [] }), IDENTITY_METAS)[0]).toEqual({
			label: 'On the disc',
			value: 'Disc text ignored',
			sub: 'See Advanced'
		});
		expect(stripCells('dvd', v({ disc_hint_sources: ['bd_title'] }), IDENTITY_METAS)[0].value).toBe(
			'Disc text ignored'
		);
	});

	it('an ignored hint drops out of cell 1', () => {
		expect(stripCells('bluray', v({ disc_hint_sources: ['label'] }), IDENTITY_METAS)[0].value).toBe('Volume label');
		expect(stripCells('cd', v({ disc_hint_sources: ['bd_title'] }), IDENTITY_METAS)[0].value).toBe(
			'Disc ID (track layout)'
		);
	});

	it('movie_auto_apply off reads Waits for review', () => {
		expect(stripCells('bluray', v({ movie_auto_apply: false }), IDENTITY_METAS)[3].value).toBe(
			'Movies: Waits for review · TV shows: Apply confident matches'
		);
		expect(stripCells('cd', v({ music_auto_apply: false }), IDENTITY_METAS)[3].value).toBe('Music: Waits for review');
	});

	it('CD cell 2 is Not used for CDs with no sub', () => {
		const cell = stripCells('cd', v({ thediscdb_enabled: false }), IDENTITY_METAS)[1];
		expect(cell).toEqual({ label: 'Disc database', value: 'Not used for CDs' });
	});
});
