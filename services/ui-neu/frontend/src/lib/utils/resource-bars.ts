// Shared helpers for the system-resource panels (BottomStatsBar + SidebarStats).

/** Usage-bar color by percent + metric kind. */
export function barColor(pct: number, kind: 'cpu' | 'mem' | 'disk'): string {
	if (pct >= 90) return 'bg-red-500';
	if (pct >= 70) return 'bg-yellow-500';
	return kind === 'cpu' ? 'bg-cyan-500' : kind === 'mem' ? 'bg-violet-500' : 'bg-emerald-500';
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

/** Deep-link href into the files browser for a storage root, e.g. `/files?root=RAW`.
 *  Falls back to `/files` when the name has no known files-browser root. */
export function filesHref(storageName: string): string {
	const key = STORAGE_TO_FILES_ROOT[storageName];
	return key ? `/files?root=${key}` : '/files';
}
