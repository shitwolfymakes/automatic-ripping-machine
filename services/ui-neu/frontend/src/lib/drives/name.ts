import type { DriveSummary } from '$lib/api/dashboard';

/**
 * Resolve a drive id to its operator-assigned friendly name.
 *
 * Single source of truth for every user-visible spot that would otherwise
 * print a raw drive id (dashboard/job cards, the job detail page, identify
 * dialogs, log rows, ...). `drives` is the dashboard store's sticky
 * `drives: Record<driveId, DriveSummary>` map (see `$lib/stores/dashboard`);
 * callers that don't have it yet (or whose drive isn't in it) fall back to
 * the raw id so the UI never renders a blank where an id used to be.
 */
export function driveLabel(driveId: string | null | undefined, drives?: Record<string, DriveSummary> | null): string {
	if (!driveId) return '';
	return drives?.[driveId]?.name ?? driveId;
}
