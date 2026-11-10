// The filters the preset libraries and the sessions hub share (media
// type, source and name), and the hub's own transcode filter.
import type { MediaType } from '$lib/types/api.gen';

/** Built-in items only, custom ones only, or both. */
export type SourceFilter = 'all' | 'builtin' | 'custom';
/** Sessions with a transcode preset, without one, or either. */
export type TranscodeFilter = 'any' | 'has' | 'none';

/** What a list is filtered by. */
export interface ListFilters {
	type: MediaType | 'all';
	source: SourceFilter;
	search: string;
}

/** The item passes the type, source and name filters. Its name passes
 * when it contains the search, ignoring case and surrounding spaces. */
export function matchesFilters(
	item: { media_type: string; is_builtin: boolean; name: string },
	filters: ListFilters
): boolean {
	if (filters.type !== 'all' && item.media_type !== filters.type) return false;
	if (filters.source === 'builtin' && !item.is_builtin) return false;
	if (filters.source === 'custom' && item.is_builtin) return false;
	const q = filters.search.trim().toLowerCase();
	if (q && !item.name.toLowerCase().includes(q)) return false;
	return true;
}

/** The session passes the transcode filter. */
export function matchesTranscode(session: { transcode_preset_id: string | null }, filter: TranscodeFilter): boolean {
	if (filter === 'has' && session.transcode_preset_id == null) return false;
	if (filter === 'none' && session.transcode_preset_id != null) return false;
	return true;
}
