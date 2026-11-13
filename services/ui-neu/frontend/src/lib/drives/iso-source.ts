// Looks up the ISO/folder source a dashboard job's drive is ripping from.
import type { IsoSourceKind } from '$lib/api/dashboard';

type DriveId = string | null | undefined;

/** The source path for a drive, or null when it has none. */
export function isoSourceFor(driveId: DriveId, sources: Record<string, string> | null | undefined): string | null {
	return driveId ? (sources?.[driveId] ?? null) : null;
}

/** The source kind for a drive; 'iso' when it has none. */
export function isoKindFor(driveId: DriveId, kinds: Record<string, IsoSourceKind> | null | undefined): IsoSourceKind {
	return driveId ? (kinds?.[driveId] ?? 'iso') : 'iso';
}
