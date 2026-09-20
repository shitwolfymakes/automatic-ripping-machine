/**
 * Resolve a drive id to its operator-assigned friendly name.
 *
 * Single source of truth for every user-visible spot that would otherwise
 * print a raw drive id (dashboard/job cards, the job detail page, identify
 * dialogs, log rows, ...). `driveNames` is the dashboard store's sticky
 * `drive_names: Record<driveId, string>` map (see `$lib/stores/dashboard`);
 * callers that don't have it yet (or whose drive isn't in it) fall back to
 * the raw id so the UI never renders a blank where an id used to be.
 */
export function driveLabel(
	driveId: string | null | undefined,
	driveNames?: Record<string, string> | null
): string {
	if (!driveId) return '';
	return driveNames?.[driveId] ?? driveId;
}
