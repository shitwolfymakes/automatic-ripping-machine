import type { StorageRoot } from '$lib/types/api.gen';
import { sharesRawDisk } from '$lib/dashboard/system-health';

// Shared helpers for the system-resource panels (BottomStatsBar + SidebarStats).

/** Usage-bar tone by percent + metric kind. Consumers set this as
 *  `data-bar` on the fill element; `.stats-bar-slot [data-bar]` (BottomStatsBar
 *  and SidebarStats scoped styles) maps it to a token colour - danger/warning
 *  override the metric's own accent once usage gets high. */
export function barColor(pct: number, kind: 'cpu' | 'mem' | 'disk'): 'danger' | 'warning' | 'cpu' | 'mem' | 'disk' {
	if (pct >= 90) return 'danger';
	if (pct >= 70) return 'warning';
	return kind;
}

// Map a /api/system/resources storage root name to the files-browser root key
// (GET /api/files/roots returns MEDIA / RAW / ISO / LOG). The resources feed
// names them MEDIA_ROOT / RAW_ROOT / LOG_DIR, so strip the suffix.
const STORAGE_TO_FILES_ROOT: Record<string, string> = {
	MEDIA_ROOT: 'MEDIA',
	RAW_ROOT: 'RAW',
	LOG_DIR: 'LOG',
	ISO_INGRESS_ROOT: 'ISO'
};

/** The storage roots that get a usage bar: every root except a staging area
 *  that shares raw's disk, which would count the same space twice. */
export function storageBars(storage: readonly StorageRoot[]): StorageRoot[] {
	return storage.filter((s) => !sharesRawDisk(s.placement));
}

/** Deep-link href into the files browser for a storage root, e.g. `/files?root=RAW`.
 *  Falls back to `/files` when the name has no known files-browser root. */
export function filesHref(storageName: string): string {
	const key = STORAGE_TO_FILES_ROOT[storageName];
	return key ? `/files?root=${key}` : '/files';
}
