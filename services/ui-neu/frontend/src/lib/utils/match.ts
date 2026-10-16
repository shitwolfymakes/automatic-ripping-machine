// Display and merge helpers for the match picker (match picker spec 4.1).
import type { ExternalIds, IdentityFacts, MetadataCandidate } from '$lib/types/api.gen';

export const RATING_LABEL: Record<string, string> = { imdb: 'IMDb', tmdb: 'TMDb', tvmaze: 'TVmaze' };

export function isSeriesKind(kind: string): boolean {
	return kind === 'tv' || kind === 'series';
}

/** "1974–1975" for a finished run; the start year alone otherwise (a running
 * show and an unknown end look the same). */
export function formatYears(year: number | null | undefined, endYear: number | null | undefined, kind: string): string {
	if (year == null) return '';
	if (isSeriesKind(kind) && endYear != null && endYear !== year) return `${year}–${endYear}`;
	return String(year);
}

export function kindLabel(kind: string): string {
	return isSeriesKind(kind) ? 'TV Series' : 'Movie';
}

export function formatVotes(n: number): string {
	if (n >= 1_000_000) return `${trim(n / 1_000_000)}M votes`;
	if (n >= 1000) return `${trim(n / 1000)}K votes`;
	return `${n} ${n === 1 ? 'vote' : 'votes'}`;
}

function trim(x: number): string {
	return x >= 10 ? String(Math.round(x)) : x.toFixed(1).replace(/\.0$/, '');
}

/** The provider's own id, which GET /api/metadata/details takes. */
export function detailsId(c: MetadataCandidate): string | null {
	const ids = c.external_ids ?? {};
	switch (c.provider) {
		case 'tmdb':
			return ids.tmdb ?? null;
		case 'omdb':
			return ids.imdb ?? c.provider_id ?? null;
		case 'tvmaze':
			return ids.tvmaze ?? null;
		case 'tvdb':
			return ids.tvdb ?? null;
		default:
			return null;
	}
}

export function candidateKey(c: MetadataCandidate): string {
	const id = detailsId(c);
	return id ? `${c.provider}:${id}` : `${c.provider ?? ''}:${c.title}:${c.year ?? ''}`;
}

function present<T extends object>(o: T | null | undefined): Partial<T> {
	return Object.fromEntries(
		Object.entries(o ?? {}).filter(([, v]) => v != null && !(Array.isArray(v) && v.length === 0))
	) as Partial<T>;
}

/** A row with its fetched details laid over it: detail values win, row
 * values the detail lacks stay. */
export function mergeCandidate(row: MetadataCandidate, detail: MetadataCandidate): MetadataCandidate {
	return {
		...row,
		...present(detail),
		external_ids: { ...(row.external_ids ?? {}), ...present<ExternalIds>(detail.external_ids) },
		facts: { ...(row.facts ?? {}), ...present<IdentityFacts>(detail.facts) } as IdentityFacts
	};
}
