// The episode sources in an identity's claims: their ids, their display
// names, and which one the resolver applied.
import type { IdentityView } from '$lib/types/api.gen';

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
