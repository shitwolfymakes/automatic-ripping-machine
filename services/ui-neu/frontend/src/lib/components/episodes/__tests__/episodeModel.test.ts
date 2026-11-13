import { describe, it, expect } from 'vitest';
import {
	failedSources,
	panelState,
	buildRows,
	placedCount,
	formatLength,
	pickerOptions,
	parseHandPick,
	pickedEpisodeName,
	usedEpisodeNumbers
} from '../../../episodes/episode-model';
import type {
	EpisodeSummary,
	IdentityView,
	TrackIdentityView,
	JobView,
	TrackView,
	MatchPreview
} from '$lib/types/api.gen';

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
			// A held result is on the tracks like a clean one; only the source's flag differs.
			role: i === 5 ? 'extra' : 'episode',
			season: i === 5 ? null : 1,
			episode_number: i === 5 ? null : i + 1,
			episode_name: i === 5 ? null : NAMES[i],
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
	it('applied / unsure; a pin is not a state', () => {
		expect(panelState(job(), identity(), false)).toBe('applied');
		// The resolver's flag on the job says a guess is applied, not the source's own suggestion flag.
		expect(panelState(job(), identity({}, true), false)).toBe('applied');
		expect(panelState(job({ episodes_unsure: true }), identity({}, true), false)).toBe('unsure');
		expect(panelState(job(), identity({ pin: { episode: 'episodes_tmdb' } }), false)).toBe('applied');
	});
	it('no match when every source missed', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'miss' }, episodes_tvdb: { status: 'skipped' } } });
		expect(panelState(job(), id, false)).toBe('nomatch');
	});
	it('no sources at all is a plain no match (cleared, or not yet run); only not-configured sources are unavailable', () => {
		expect(panelState(job(), identity({ sources: {} }), false)).toBe('nomatch');
		const off = { status: 'skipped', detail: 'not configured' } as const;
		expect(panelState(job(), identity({ sources: { episodes_tmdb: off, episodes_tvmaze: off } }), false)).toBe(
			'unavailable'
		);
	});
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
		// The picker's own value: the episode as pickerOptions values it, a role for an extra.
		expect(rows[0].pickValue).toBe('s1e1');
		expect(rows[5].pickValue).toBe('extra');
	});
	it('rows placed by a held source are a guess only while the job is unsure', () => {
		const rows = buildRows(tracks, identity({}, true), null, true);
		expect(rows[0]).toMatchObject({
			code: 'S01E01',
			origin: { kind: 'guess', source: 'episodes_tmdb' },
			confidence: 0.6
		});
		// Resolved sure since (a clean result won): the same rows read as auto.
		expect(buildRows(tracks, identity({}, true), null)[0].origin.kind).toBe('auto');
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
	it('a seasonless episode renders no season, never an assumed one', () => {
		const id = identity();
		id.tracks![2].season = null;
		expect(buildRows(tracks, id, null)[2].code).toBe('S-E03');
	});
	it('carries the saved season and the length in seconds', () => {
		const id = identity();
		id.tracks![1].season = null;
		const withSeason = tracks.map((t, i) => (i === 1 ? { ...t, season: 3 } : t));
		const rows = buildRows(withSeason, id, null);
		expect(rows[0]).toMatchObject({ season: 1, seconds: 3093 });
		expect(rows[1].season).toBe(3);
		expect(rows[5]).toMatchObject({ season: null, seconds: 542 });
	});
});

it('formatLength', () => {
	expect(formatLength(3093)).toBe('51:33');
	expect(formatLength(542)).toBe('9:02');
	expect(formatLength(null)).toBe('-');
});
describe('fix round 1', () => {
	const errOnly = () =>
		identity({ sources: { episodes_tmdb: { status: 'error', detail: 'boom' }, episodes_tvdb: { status: 'error' } } });
	it('error-only is nomatch and names the failed sources', () => {
		expect(panelState(job(), errOnly(), false)).toBe('nomatch');
		expect(failedSources(errOnly())).toEqual([
			{ id: 'episodes_tmdb', label: 'TMDb', detail: 'boom' },
			{ id: 'episodes_tvdb', label: 'TVDB', detail: null }
		]);
	});
	it('miss+error is nomatch, listing only the error', () => {
		const id = identity({
			sources: { episodes_tmdb: { status: 'miss' }, episodes_tvmaze: { status: 'error', detail: 'x' } }
		});
		expect(panelState(job(), id, false)).toBe('nomatch');
		expect(failedSources(id).map((f) => f.id)).toEqual(['episodes_tvmaze']);
	});
	it('ok+error is applied', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'ok' }, episodes_tvdb: { status: 'error' } } });
		expect(panelState(job(), id, false)).toBe('applied');
	});
	it('any manual provenance value makes the row hand-set', () => {
		const id = identity();
		id.tracks![0].identity_provenance = { role: 'manual', episode_number: 'episodes_tmdb' };
		expect(buildRows(tracks, id, null)[0]).toMatchObject({ handSet: true, origin: { kind: 'you' } });
	});
	it('precedence: matching > unsure; manual-only is a plain no match', () => {
		expect(panelState(job({ episodes_unsure: true }), identity({}, true), true)).toBe('matching');
		expect(
			panelState(job({ episodes_unsure: true }), identity({ pin: { episode: 'episodes_tmdb' } }, true), false)
		).toBe('unsure');
		expect(panelState(job(), identity({ sources: { manual: { status: 'ok' } } }), false)).toBe('nomatch');
	});
});

describe('pickerOptions', () => {
	it('sorts picker options by runtime fit and pushes used episodes last', () => {
		const eps = [
			{ number: 1, name: 'A', runtime_s: 2700 },
			{ number: 2, name: 'B', runtime_s: 1500 },
			{ number: 3, name: 'C', runtime_s: 1520 }
		] as any;
		const labels = pickerOptions(eps, 2, 1510, new Set([3])).map((o) => o.label);
		expect(labels.slice(0, 3)).toEqual(['E02 B, 25m', 'E01 A, 45m', 'E03 C, 25m (used)']);
		expect(pickerOptions(eps, 2, 1510, new Set())[0].value).toBe('s2e2');
	});
	it('labels specials as season 0, puts unknown runtimes last, then the roles', () => {
		const eps = [
			{ number: 2, name: 'No runtime' },
			{ number: 1, name: 'Pilot', runtime_s: 4440, special: true },
			{ number: 1, name: 'First', runtime_s: 3000 }
		];
		expect(pickerOptions(eps, 1, 3000, new Set()).map((o) => [o.value, o.label])).toEqual([
			['s1e1', 'E01 First, 50m'],
			['s0e1', 'S00E01 Pilot, 74m, special'],
			['s1e2', 'E02 No runtime'],
			['extra', 'Extra'],
			['trailer', 'Trailer'],
			['other', 'Other']
		]);
	});
	it('orders by number when the track length is unknown', () => {
		const eps = [
			{ number: 3, name: 'C', runtime_s: 100 },
			{ number: 1, name: 'A', runtime_s: 900 }
		];
		expect(pickerOptions(eps, 1, null, new Set()).map((o) => o.value)).toEqual([
			's1e1',
			's1e3',
			'extra',
			'trailer',
			'other'
		]);
	});
});

describe('placedCount', () => {
	const row = (code: string, kind: 'auto' | 'guess' | 'you' | 'none') =>
		({ code, origin: { kind, source: kind === 'none' ? null : 'episodes_tmdb' } }) as unknown as ReturnType<
			typeof buildRows
		>[number];

	it('counts every placement on the tracks, a guess included', () => {
		const rows = [
			row('S01E01', 'auto'),
			row('S01E02', 'you'),
			row('Extra', 'none'),
			row('S01E04', 'guess'),
			row('Not placed', 'none')
		];
		expect(placedCount(rows)).toBe(4);
	});
});

describe('usedEpisodeNumbers', () => {
	const held = (trackId: string, season: number | null, episode: number | null, end?: number) =>
		({ track_id: trackId, season, episode_number: episode, episode_number_end: end }) as TrackIdentityView;

	it('leaves out the asking track own episode', () => {
		expect(usedEpisodeNumbers([held('a', 1, 2), held('b', 1, 3)], 1, 'a')).toEqual(new Set([3]));
	});

	it('leaves out the tracks of another season', () => {
		expect(usedEpisodeNumbers([held('a', 2, 2), held('b', 1, 3)], 1, 'z')).toEqual(new Set([3]));
	});

	it('leaves out a track with no episode', () => {
		expect(usedEpisodeNumbers([held('a', 1, null), held('b', 1, 3)], 1, 'z')).toEqual(new Set([3]));
	});

	it('adds the whole span of a two-part track', () => {
		expect(usedEpisodeNumbers([held('a', 1, 4, 6)], 1, 'z')).toEqual(new Set([4, 5, 6]));
	});

	it('adds up several tracks', () => {
		expect(usedEpisodeNumbers([held('a', 1, 1), held('b', 1, 2, 3)], 1, 'z')).toEqual(new Set([1, 2, 3]));
	});

	it('gives an empty set for no tracks', () => {
		expect(usedEpisodeNumbers([], 1, 'z')).toEqual(new Set());
	});
});

describe('parseHandPick', () => {
	it.each(['extra', 'trailer', 'other'])('reads %s as that role', (role) => {
		expect(parseHandPick(role)).toEqual({ role });
	});

	it('reads s2e5 as season 2, episode 5', () => {
		expect(parseHandPick('s2e5')).toEqual({ season: 2, episode: 5 });
	});

	it('reads s0e3 as season 0, episode 3', () => {
		expect(parseHandPick('s0e3')).toEqual({ season: 0, episode: 3 });
	});

	it.each(['', 'episode', 's2', 's2e', 'x2e5'])('gives null for %j', (value) => {
		expect(parseHandPick(value)).toBeNull();
	});

	it('reads back every value pickerOptions gives', () => {
		const eps = [
			{ number: 1, name: 'First', runtime_s: 3000 },
			{ number: 4, name: 'Fourth' },
			{ number: 2, name: 'Pilot', special: true }
		] as EpisodeSummary[];
		const picks = pickerOptions(eps, 3, 3000, new Set([4])).map((o) => [o.value, parseHandPick(o.value)]);
		expect(picks).toEqual([
			['s3e1', { season: 3, episode: 1 }],
			['s0e2', { season: 0, episode: 2 }],
			['s3e4', { season: 3, episode: 4 }],
			['extra', { role: 'extra' }],
			['trailer', { role: 'trailer' }],
			['other', { role: 'other' }]
		]);
	});
});

describe('pickedEpisodeName', () => {
	const list = [
		{ number: 1, name: 'First' },
		{ number: 2 },
		{ number: 1, name: 'Pilot', special: true }
	] as EpisodeSummary[];

	it('gives the name of a regular episode', () => {
		expect(pickedEpisodeName(list, 1, 1, 1)).toBe('First');
	});

	it('gives null when the list does not hold the episode', () => {
		expect(pickedEpisodeName(list, 1, 1, 9)).toBeNull();
	});

	it('gives null for a found episode with no name', () => {
		expect(pickedEpisodeName(list, 1, 1, 2)).toBeNull();
	});

	it('takes a special for a season 0 pick from a regular season list', () => {
		expect(pickedEpisodeName(list, 1, 0, 1)).toBe('Pilot');
	});

	it('does not take a regular episode of the same number for a season 0 pick', () => {
		expect(pickedEpisodeName([list[0]], 1, 0, 1)).toBeNull();
	});

	it('does not take a special for a regular season pick', () => {
		expect(pickedEpisodeName([list[2]], 1, 1, 1)).toBeNull();
	});

	it('matches every episode of a season 0 list to a season 0 pick', () => {
		expect(pickedEpisodeName([list[0]], 0, 0, 1)).toBe('First');
	});

	it('gives null for no list', () => {
		expect(pickedEpisodeName([], null, 1, 1)).toBeNull();
	});
});
