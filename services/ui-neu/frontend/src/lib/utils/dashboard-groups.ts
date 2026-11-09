// Sorts the dashboard's active jobs into its sections, and finds the jobs
// that have newly entered review. Pure rules; the page owns the state.
import type { JobView } from '$lib/types/api.gen';
import { isAwaitingAction } from '$lib/utils/job-status';
import { isReviewCardStatus } from '$lib/utils/job-status-groups';

export interface ActiveJobGroups {
	scanning: JobView[];
	waiting: JobView[];
	ripping: JobView[];
	finishing: JobView[];
}

// Whether a job shows as a review card in the Waiting section.
function isWaiting(j: JobView, dismissed: ReadonlySet<string>, sticky: ReadonlySet<string>): boolean {
	if (dismissed.has(j.id)) return false;
	// In review while awaiting (incl. awaiting_review), sticky after an apply
	// promoted it to identified, OR post-rip awaiting a transcode session
	// (ripped/ripped_partial, no session in flight) — these come BACK as a
	// rich review card so the operator can apply a session + fix metadata.
	return (
		isReviewCardStatus(j.status ?? '') ||
		(sticky.has(j.id) && j.status?.toLowerCase() === 'identified') ||
		isAwaitingAction(j)
	);
}

export function groupActiveJobs(
	active: JobView[],
	dismissed: ReadonlySet<string>,
	sticky: ReadonlySet<string>
): ActiveJobGroups {
	const scanning = active.filter((j) => j.status?.toLowerCase() === 'created');
	const waiting = active.filter((j) => isWaiting(j, dismissed, sticky));
	const waitingIds = new Set(waiting.map((j) => j.id));
	const ripping = active.filter((j) => j.status?.toLowerCase() === 'ripping');
	// A sticky review card that promoted to `identified` shows in Waiting, not
	// also in Finishing — exclude anything currently rendered as a review card.
	const finishing = active.filter((j) => isAwaitingAction(j) && !waitingIds.has(j.id));
	return { scanning, waiting, ripping, finishing };
}

// Ids of jobs that are in review now but not yet remembered as sticky.
export function newReviewIds(active: JobView[], sticky: ReadonlySet<string>): string[] {
	return active.filter((j) => isReviewCardStatus(j.status ?? '') && !sticky.has(j.id)).map((j) => j.id);
}
