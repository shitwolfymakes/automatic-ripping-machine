// Lookups over the dashboard's per-drive records (DashboardData.drives).
import type { DriveSummary, IsoSourceKind } from '$lib/api/dashboard';

/** A drive that is reading from an ISO or a folder right now. */
export type LiveSourceDrive = DriveSummary & { source: IsoSourceKind };

/** The record for a drive, or null when the id is missing or unknown. */
export function driveSummary(
	drives: Record<string, DriveSummary> | null | undefined,
	driveId: string | null | undefined
): DriveSummary | null {
	return driveId ? (drives?.[driveId] ?? null) : null;
}

/** The drive when it is a virtual drive still reading its source; null otherwise. */
export function liveSource(drive: DriveSummary | null | undefined): LiveSourceDrive | null {
	return drive?.source && !drive.retired ? { ...drive, source: drive.source } : null;
}
