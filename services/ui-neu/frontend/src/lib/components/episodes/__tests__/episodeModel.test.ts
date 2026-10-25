import { describe, it, expect } from 'vitest';
import {
	failedSources,
	panelState,
	buildRows,
	placedCount,
	formatLength,
	activeSource,
	holdReasons,
	seasonAlternatives,
	heldSeason,
	holdHeadline,
	pickerOptions
} from '../episodeModel';
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
	});
	it('rows placed by a held source are a guess', () => {
		const rows = buildRows(tracks, identity({}, true), null);
		expect(rows[0]).toMatchObject({
			code: 'S01E01',
			origin: { kind: 'guess', source: 'episodes_tmdb' },
			confidence: 0.6
		});
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
it('activeSource maps a pin to its source id', () => {
	expect(activeSource(identity({ pin: { episode: 'episodes_tvmaze' } }))).toBe('episodes_tvmaze');
});
it('activeSource also tolerates a bare setting name and ignores the manual claims entry', () => {
	expect(activeSource(identity({ pin: { episode: 'tvdb' } }))).toBe('episodes_tvdb');
	expect(activeSource(identity({ sources: { manual: { status: 'ok' }, episodes_tvmaze: { status: 'ok' } } }))).toBe(
		'episodes_tvmaze'
	);
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

describe('activeSource agrees with the resolver', () => {
	const tvmazeApplied = (): IdentityView => {
		const base = identity();
		return {
			...base,
			sources: { episodes_tmdb: { status: 'ok', suggestion: true }, episodes_tvmaze: { status: 'ok' } },
			tracks: (base.tracks ?? []).map((t) =>
				t.role === 'extra' ? t : { ...t, identity_provenance: { episode_number: 'episodes_tvmaze' } }
			)
		};
	};
	it('the source named in the tracks provenance beats an earlier unpinned suggestion', () => {
		expect(activeSource(tvmazeApplied())).toBe('episodes_tvmaze');
		expect(panelState(job(), tvmazeApplied(), false)).toBe('applied');
	});
	it('without provenance a non-suggestion ok source beats a suggestion', () => {
		const id = { ...tvmazeApplied(), tracks: [] };
		expect(activeSource(id)).toBe('episodes_tvmaze');
	});
	it('falls back to an ok suggestion when nothing else is ok', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'ok', suggestion: true } }, tracks: [] });
		expect(activeSource(id)).toBe('episodes_tmdb');
	});
});

describe('season candidates and hold reasons', () => {
	it('maps hold reason codes to sentences and drops unknown ones', () => {
		const id = {
			sources: { episodes_tmdb: { status: 'ok', suggestion: true, extra: { hold_reasons: ['near_tie', 'bogus'] } } }
		} as unknown as IdentityView;
		expect(holdReasons(id, 'episodes_tmdb')).toEqual(['Another season fits about as well.']);
	});
	it('lists candidate seasons from alternatives', () => {
		const id = {
			sources: {
				episodes_tmdb: {
					status: 'ok',
					alternatives: [
						{ season: 3, coverage: 0.75, matches: 3 },
						{ season: 4, matches: 2 }
					]
				}
			}
		} as unknown as IdentityView;
		// The total is the season's own title count (3 / 0.75 = 4), not the rows shown.
		expect(seasonAlternatives(id, 'episodes_tmdb', 6)).toEqual([
			{ season: 3, matches: 3, total: 4 },
			{ season: 4, matches: 2, total: 6 }
		]);
		expect(seasonAlternatives(id, 'episodes_tmdb')[1].total).toBe(0);
		expect(seasonAlternatives(id, null)).toEqual([]);
	});
	it('names the held season from the source proposals', () => {
		const id = {
			sources: { episodes_tmdb: { status: 'ok', suggestion: true } },
			tracks: [
				{ track_id: 'a', proposals: { episodes_tmdb: { season: 5, episode: 1 } } },
				{ track_id: 'b', proposals: { episodes_tmdb: { season: 5, episode: 2 } } },
				{ track_id: 'c', proposals: { episodes_tmdb: { role: 'extra' } } }
			]
		} as unknown as IdentityView;
		expect(heldSeason(id, 'episodes_tmdb', 3)).toEqual({ season: 5, matches: 2, total: 3 });
		expect(heldSeason(id, 'episodes_tvmaze', 3)).toBeNull();
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

describe('holdHeadline', () => {
	const held = (codes: string[]): IdentityView => ({
		sources: { episodes_tmdb: { status: 'ok', suggestion: true, extra: { hold_reasons: codes } } },
		pin: {},
		tracks: []
	});

	it('names the season and the strongest reason, keeping the rest', () => {
		expect(holdHeadline(held(['near_tie', 'nominal_runtimes']), 'episodes_tmdb', 3)).toEqual({
			line: 'Season 3 is a guess: another season fits about as well.',
			more: ['The source lists rounded runtimes, not real ones.']
		});
	});

	it('falls back to the match when the season is unknown, and to a bare line with no reason', () => {
		expect(holdHeadline(held(['ambiguous']), 'episodes_tmdb', null).line).toBe(
			'This match is a guess: the titles fit equally well one episode earlier or later.'
		);
		expect(holdHeadline(held([]), 'episodes_tmdb', 0)).toEqual({ line: 'Specials is a guess.', more: [] });
	});
});
