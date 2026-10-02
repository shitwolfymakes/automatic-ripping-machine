import { describe, it, expect } from 'vitest';
import { panelState, buildRows, placedCount, formatLength, activeSource } from '../episodeModel';
import type { IdentityView, TrackIdentityView, JobView, TrackView, MatchPreview } from '$lib/types/api.gen';

const job = (o: Partial<JobView> = {}) =>
	({ has_series: true, looks_episodic: true, media_type: 'tv', ...o }) as JobView;
const LENGTHS = [3093, 3033, 3092, 3070, 3078, 542];
const NAMES = ['The Ripper', 'The Zombie', 'They Have Been, They Are, They Will Be...', 'The Vampire', 'The Werewolf'];
const tracks = LENGTHS.map((d, i) => ({ id: `trk_${i}`, source_ref: `t0${i}`, duration_seconds: d }) as TrackView);

function identity(o: Partial<IdentityView> = {}, suggestion = false): IdentityView {
	return {
		sources: { episodes_tmdb: { status: 'ok', suggestion } },
		pin: {},
		tracks: LENGTHS.map((_, i): TrackIdentityView => ({
			track_id: `trk_${i}`,
			source_ref: `t0${i}`,
			role: i === 5 ? 'extra' : 'episode',
			season: i === 5 || suggestion ? null : 1,
			episode_number: i === 5 || suggestion ? null : i + 1,
			episode_name: i === 5 || suggestion ? null : NAMES[i],
			identity_provenance: i === 5 ? {} : { episode_number: 'episodes_tmdb' },
			proposals:
				i === 5
					? {}
					: { episodes_tmdb: { season: 1, episode: i + 1, episode_name: NAMES[i], confidence: suggestion ? 0.6 : 0.9 } }
		})),
		...o
	};
}

describe('panelState', () => {
	it('asks for the series when none is known (e.g. a movie id)', () => {
		expect(panelState(job({ has_series: false }), identity(), false)).toBe('noseries');
	});
	it('matching wins over stored rows', () => expect(panelState(job(), identity(), true)).toBe('matching'));
	it('applied / suggestion / pinned', () => {
		expect(panelState(job(), identity(), false)).toBe('applied');
		expect(panelState(job(), identity({}, true), false)).toBe('suggestion');
		expect(panelState(job(), identity({ pin: { episode: 'episodes_tmdb' } }), false)).toBe('pinned');
	});
	it('no match when every source missed', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'miss' }, episodes_tvdb: { status: 'skipped' } } });
		expect(panelState(job(), id, false)).toBe('nomatch');
	});
	it('unavailable with no sources at all', () =>
		expect(panelState(job(), identity({ sources: {} }), false)).toBe('unavailable'));
});

describe('buildRows', () => {
	it('applied rows read Kolchak disc 1', () => {
		const rows = buildRows(tracks, identity(), null);
		expect(rows.map((r) => r.code)).toEqual(['S01E01', 'S01E02', 'S01E03', 'S01E04', 'S01E05', 'Extra']);
		expect(rows[3]).toMatchObject({
			ref: 't03',
			length: '51:10',
			name: 'The Vampire',
			origin: { kind: 'auto', source: 'episodes_tmdb' },
			confidence: 0.9
		});
		expect(rows[5].origin.kind).toBe('none');
		expect(placedCount(rows)).toBe(6);
	});
	it('suggestion rows come from the proposals and say so', () => {
		const rows = buildRows(tracks, identity({}, true), null);
		expect(rows[0]).toMatchObject({ code: 'S01E01', origin: { kind: 'suggestion' }, confidence: 0.6 });
	});
	it('a hand-set row is "you"', () => {
		const id = identity();
		id.tracks![5].identity_provenance = { role: 'manual' };
		expect(buildRows(tracks, id, null)[5]).toMatchObject({ handSet: true, origin: { kind: 'you' } });
	});
	it('a preview marks changed rows', () => {
		const preview: MatchPreview = {
			outcomes: [
				{
					source_id: 'episodes_tvmaze',
					matches: [
						{ source_ref: 't00', season: 1, episode: 2, episode_name: 'The Zombie', confidence: 0.81 },
						{ source_ref: 't01', season: 1, episode: 1, episode_name: 'The Ripper', confidence: 0.79 },
						{ source_ref: 't02', season: 1, episode: 3, episode_name: NAMES[2], confidence: 0.9 }
					]
				}
			]
		};
		const rows = buildRows(tracks, identity(), preview);
		expect(rows.filter((r) => r.changed).map((r) => r.ref)).toEqual(['t00', 't01']);
		expect(rows[0].proposed).toEqual({ code: 'S01E02', name: 'The Zombie', confidence: 0.81 });
	});
	it('a span renders E03-E04', () => {
		const id = identity();
		id.tracks![2].episode_number_end = 4;
		expect(buildRows(tracks, id, null)[2].code).toBe('S01E03-E04');
	});
});

it('formatLength', () => {
	expect(formatLength(3093)).toBe('51:33');
	expect(formatLength(542)).toBe('9:02');
	expect(formatLength(null)).toBe('—');
});
it('activeSource maps a pin to its source id', () => {
	expect(activeSource(identity({ pin: { episode: 'episodes_tvmaze' } }))).toBe('episodes_tvmaze');
});
it('activeSource also tolerates a bare setting name and ignores the manual claims entry', () => {
	expect(activeSource(identity({ pin: { episode: 'tvdb' } }))).toBe('episodes_tvdb');
	expect(activeSource(identity({ sources: { manual: { status: 'ok' }, episodes_tvmaze: { status: 'ok' } } }))).toBe(
		'episodes_tvmaze'
	);
});
