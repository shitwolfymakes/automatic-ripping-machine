// The episode sources in an identity's claims: their ids, their display
// names, and which one the resolver applied.
import type { IdentityView, SourceSummary } from '$lib/types/api.gen';
import type { EpisodeSource } from '$lib/api/identity';

export const SOURCE_LABEL: Record<string, string> = {
	episodes_tmdb: 'TMDb',
	episodes_tvmaze: 'TVmaze',
	episodes_tvdb: 'TVDB'
};
export const EPISODE_PREFIX = 'episodes_';

/** The episode source the resolver applied, in its order: the pin, then the
 * source the tracks' provenance names (what actually won), then the first ok
 * clean source, then the first ok held source (applied as a guess). */
export function activeSource(identity: IdentityView): string | null {
	const pinned = identity.pin?.episode;
	if (pinned) return pinned.startsWith(EPISODE_PREFIX) ? pinned : `${EPISODE_PREFIX}${pinned}`;
	const sources = identity.sources ?? {};
	const ok = Object.keys(sources).filter((id) => id.startsWith(EPISODE_PREFIX) && sources[id]?.status === 'ok');
	const counts = new Map<string, number>();
	for (const t of identity.tracks ?? []) {
		for (const src of Object.values(t.identity_provenance ?? {})) {
			if (ok.includes(src)) counts.set(src, (counts.get(src) ?? 0) + 1);
		}
	}
	let applied: string | null = null;
	let best = 0;
	for (const [src, n] of counts) {
		if (n > best) {
			applied = src;
			best = n;
		}
	}
	return applied ?? ok.find((id) => !sources[id]?.suggestion) ?? ok[0] ?? null;
}

/** The episode sources the panel can run, by their short ids, in the
 * order it offers them. */
export const EPISODE_SOURCES: EpisodeSource[] = ['tmdb', 'tvmaze', 'tvdb'];

/** One choice of the Fix match form's source select. */
export interface EpisodeSourceOption {
	id: EpisodeSource;
	label: string;
	/** Skipped as not configured: the source can't run. */
	disabled: boolean;
}

/** A source the resolver skipped because it is not configured: it can't
 * run until it is set up in Settings. */
export function notConfigured(claim: SourceSummary | undefined): boolean {
	return claim?.status === 'skipped' && /not configured/i.test(claim?.detail ?? '');
}

/** The Fix match form's source choices, in EPISODE_SOURCES order. A
 * source the identity records as skipped for not being configured is
 * off. */
export function episodeSourceOptions(identity: IdentityView | null): EpisodeSourceOption[] {
	return EPISODE_SOURCES.map((id) => {
		const s = identity?.sources?.[`episodes_${id}`];
		const off = notConfigured(s);
		return { id, label: SOURCE_LABEL[`episodes_${id}`], disabled: off };
	});
}

/** A short source id's label ("tmdb" is "TMDb"). An id with no label is
 * its own label, and no id is ''. */
export function shortSourceLabel(id: string | null | undefined): string {
	return SOURCE_LABEL[`episodes_${id}`] ?? id ?? '';
}

/** A source claim's id without its `episodes_` prefix. */
export function shortSourceId(id: string | null): EpisodeSource {
	return (id ?? '').replace(/^episodes_/, '') as EpisodeSource;
}

/** The source the per-row picker lists episodes from: the active source,
 * else the first of EPISODE_SOURCES that ran and could answer (ok or
 * miss); null when none did. */
export function pickerSourceFor(identity: IdentityView | null, active: string | null): EpisodeSource | null {
	if (active) return shortSourceId(active);
	const ran = EPISODE_SOURCES.find((id) => {
		const st = identity?.sources?.[`episodes_${id}`]?.status;
		return st === 'ok' || st === 'miss';
	});
	return ran ?? null;
}
