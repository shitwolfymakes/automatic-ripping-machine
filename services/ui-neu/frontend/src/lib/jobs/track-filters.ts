// A rip preset's custom track filters (its track_filters_json) and the
// parsing behind their inputs.

import type { TrackSelection } from '$lib/types/api.gen';

/** The `track_filters_json` shape; all conditions are ANDed. */
export type TrackFilters = {
	min_duration_seconds?: number | null;
	max_duration_seconds?: number | null;
	title_indices?: number[] | null; // allowlist
	title_indices_exclude?: number[] | null; // blocklist
};

/**
 * The positive whole numbers in a comma- or space-separated list.
 */
export function parseIndexList(v: string): number[] {
	return v
		.split(/[ ,]+/)
		.map((s) => Number(s))
		.filter((n) => Number.isInteger(n) && n > 0);
}

/** A duration input's seconds; null when blank. */
export function parseDuration(v: string): number | null {
	return v ? Number(v) : null;
}

/**
 * The `track_filters_json` a rip preset request sends. It is an * object only for the custom selection, with its null and
 * undefined keys dropped; null otherwise.
 */
export function trackFiltersBody(selection: TrackSelection, filters: TrackFilters): TrackFilters | null {
	if (selection !== 'custom') return null;
	return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== null && v !== undefined)) as TrackFilters;
}
