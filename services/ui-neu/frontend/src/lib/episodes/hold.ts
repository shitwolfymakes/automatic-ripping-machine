// A held episode match: why the source's result was held, the season it
// guessed, and the other seasons its scan found a fit in.
import type { IdentityView } from '$lib/types/api.gen';

/** Why a held (suggestion) result was not applied, by the backend's
 * `extra.hold_reasons` code (design spec 2026-10-23 section 4.2 E). */
export const HOLD_REASON_TEXT: Record<string, string> = {
	ambiguous: 'The titles fit equally well one episode earlier or later.',
	near_tie: 'Another season fits about as well.',
	low_coverage: 'Fewer than half the titles found an episode.',
	low_confidence: 'The runtimes are a loose fit.',
	thin_win: 'The best season wins by a thin margin.',
	nominal_runtimes: 'The source lists rounded runtimes, not real ones.',
	sibling_conflict: 'Another disc of this season already holds some of these episodes, or its disc number is unknown.',
	auto_apply_off: 'Automatic apply is off in Settings.'
};

export interface SeasonCandidate {
	season: number;
	matches: number;
	total: number;
}

export function holdReasons(identity: IdentityView, source: string | null): string[] {
	const codes = source ? identity.sources?.[source]?.extra?.hold_reasons : null;
	if (!Array.isArray(codes)) return [];
	return codes.map((c) => HOLD_REASON_TEXT[String(c)]).filter((t): t is string => !!t);
}

/** The one-line reading of a held result: the season the source guessed and
 * its strongest reason, with the other reasons kept for a disclosure. */
export function holdHeadline(
	identity: IdentityView,
	source: string | null,
	season: number | null
): { line: string; more: string[] } {
	const reasons = holdReasons(identity, source);
	const subject = season == null ? 'This match' : season === 0 ? 'Specials' : `Season ${season}`;
	const [first, ...more] = reasons;
	const line = first
		? `${subject} is a guess: ${first.charAt(0).toLowerCase()}${first.slice(1)}`
		: `${subject} is a guess.`;
	return { line, more };
}

/** The other seasons the source's scan found a fit in, best first. Each
 * total is the number of titles that season was matched over (its matches
 * over its coverage); `fallback` stands in when the coverage is unknown. */
export function seasonAlternatives(identity: IdentityView, source: string | null, fallback = 0): SeasonCandidate[] {
	const alts = source ? (identity.sources?.[source]?.alternatives ?? []) : [];
	return alts
		.filter((a) => typeof a.season === 'number')
		.map((a) => {
			const matches = Number(a.matches ?? 0);
			const coverage = Number(a.coverage ?? 0);
			const total = coverage > 0 ? Math.round(matches / coverage) : fallback;
			return { season: a.season as number, matches, total };
		});
}

/** The season the source's own (held) result placed the tracks in, by its
 * per-track proposals; null when it proposed no episode. */
export function heldSeason(identity: IdentityView, source: string | null, total = 0): SeasonCandidate | null {
	if (!source) return null;
	const counts = new Map<number, number>();
	for (const t of identity.tracks ?? []) {
		const p = t.proposals?.[source];
		if (p?.season != null && p.episode != null) counts.set(p.season, (counts.get(p.season) ?? 0) + 1);
	}
	let best: SeasonCandidate | null = null;
	for (const [season, matches] of counts) if (!best || matches > best.matches) best = { season, matches, total };
	return best;
}
