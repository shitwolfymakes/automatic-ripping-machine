import { describe, it, expect } from 'vitest';
import { activeSource } from '../episode-sources';
import { panelState } from '$lib/components/episodes/episodeModel';
import type { IdentityView, TrackIdentityView, JobView } from '$lib/types/api.gen';

const job = (o: Partial<JobView> = {}) =>
	({ has_series: true, looks_episodic: true, media_type: 'tv', ...o }) as JobView;
const LENGTHS = [3093, 3033, 3092, 3070, 3078, 542];
const NAMES = ['The Ripper', 'The Zombie', 'They Have Been, They Are, They Will Be...', 'The Vampire', 'The Werewolf'];

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

it('activeSource maps a pin to its source id', () => {
	expect(activeSource(identity({ pin: { episode: 'episodes_tvmaze' } }))).toBe('episodes_tvmaze');
});
it('activeSource also tolerates a bare setting name and ignores the manual claims entry', () => {
	expect(activeSource(identity({ pin: { episode: 'tvdb' } }))).toBe('episodes_tvdb');
	expect(activeSource(identity({ sources: { manual: { status: 'ok' }, episodes_tvmaze: { status: 'ok' } } }))).toBe(
		'episodes_tvmaze'
	);
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
	it('without a tracks list a non-suggestion ok source is still chosen', () => {
		const id = { ...tvmazeApplied(), tracks: undefined };
		expect(activeSource(id)).toBe('episodes_tvmaze');
	});
	const withProvenance = (provenance: (string | null)[]): IdentityView => {
		const base = identity();
		return {
			...base,
			sources: { episodes_tmdb: { status: 'ok' }, episodes_tvmaze: { status: 'ok' } },
			tracks: provenance.map((src, i) => ({
				...(base.tracks ?? [])[i],
				identity_provenance: (src ? { episode_number: src } : {}) as Record<string, string>
			}))
		};
	};
	it('the source with more provenance counts wins over one counted first', () => {
		expect(activeSource(withProvenance(['episodes_tmdb', 'episodes_tvmaze', 'episodes_tvmaze']))).toBe(
			'episodes_tvmaze'
		);
	});
	it('the source counted first keeps the win when the later one has fewer or equal counts', () => {
		expect(activeSource(withProvenance(['episodes_tmdb', 'episodes_tmdb', 'episodes_tvmaze']))).toBe('episodes_tmdb');
		expect(activeSource(withProvenance(['episodes_tmdb', 'episodes_tvmaze']))).toBe('episodes_tmdb');
	});
	it('an identity without sources has no active source', () => {
		expect(activeSource(identity({ sources: undefined, tracks: [] }))).toBeNull();
	});
	it('a track without provenance counts for no source', () => {
		const base = identity();
		const bare = (base.tracks ?? []).map((t) => ({ ...t, identity_provenance: undefined }));
		expect(activeSource({ ...base, tracks: bare })).toBe('episodes_tmdb');
	});
	it('falls back to an ok suggestion when nothing else is ok', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'ok', suggestion: true } }, tracks: [] });
		expect(activeSource(id)).toBe('episodes_tmdb');
	});
});
