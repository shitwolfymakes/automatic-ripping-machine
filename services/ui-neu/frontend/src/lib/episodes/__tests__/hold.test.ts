import { describe, it, expect } from 'vitest';
import { holdReasons, seasonAlternatives, heldSeason, holdHeadline } from '../hold';
import type { IdentityView, TrackIdentityView } from '$lib/types/api.gen';

const ident = (o: Record<string, unknown> = {}) => ({ pin: {}, ...o }) as unknown as IdentityView;
const proposing = (season: number | null, episode: number | null) =>
	({ track_id: 't', proposals: { episodes_tmdb: { season, episode } } }) as unknown as TrackIdentityView;

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

describe('holdReasons', () => {
	it('a null source has no reasons', () => {
		expect(holdReasons(ident(), null)).toEqual([]);
	});
});

describe('seasonAlternatives', () => {
	it('an alternative with no matches counts 0', () => {
		const id = ident({ sources: { episodes_tmdb: { alternatives: [{ season: 2 }] } } });
		expect(seasonAlternatives(id, 'episodes_tmdb', 7)).toEqual([{ season: 2, matches: 0, total: 7 }]);
	});
	it('a source with no alternatives gives none', () => {
		const id = ident({ sources: { episodes_tmdb: {} } });
		expect(seasonAlternatives(id, 'episodes_tmdb')).toEqual([]);
	});
});

describe('heldSeason', () => {
	it('a null source gives null', () => {
		expect(heldSeason(ident(), null)).toBeNull();
	});
	it('an identity with no tracks gives null', () => {
		expect(heldSeason(ident(), 'episodes_tmdb')).toBeNull();
	});
	it('a later season with fewer proposals keeps the best', () => {
		const tracks = [proposing(1, 1), proposing(1, 2), proposing(2, 1)];
		expect(heldSeason(ident({ tracks }), 'episodes_tmdb', 9)).toEqual({ season: 1, matches: 2, total: 9 });
	});
	it('a later season with equal proposals keeps the first', () => {
		const tracks = [proposing(1, 1), proposing(2, 1)];
		expect(heldSeason(ident({ tracks }), 'episodes_tmdb')).toEqual({ season: 1, matches: 1, total: 0 });
	});
});
