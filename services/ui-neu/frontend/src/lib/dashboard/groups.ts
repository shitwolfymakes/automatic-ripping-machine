// Sorts the dashboard's active jobs into its sections. Pure rules; the page
// owns the state.
import type { JobView } from '$lib/types/api.gen';
import { isAwaitingAction } from '$lib/jobs/status';
import { isReviewCardStatus } from '$lib/jobs/status-groups';

export interface ActiveJobGroups {
	scanning: JobView[];
	waiting: JobView[];
	ripping: JobView[];
	finishing: JobView[];
}

// Whether a job shows as a review card in the Waiting section.
function isWaiting(j: JobView, dismissed: ReadonlySet<string>): boolean {
	if (dismissed.has(j.id)) return false;
	// In review (awaiting identification or review, or identified and waiting
	// to start), OR post-rip awaiting a transcode session (ripped/ripped_partial,
	// no session in flight) — these come BACK as a rich review card so the
	// operator can apply a session + fix metadata.
	return isReviewCardStatus(j.status ?? '') || isAwaitingAction(j);
}

export function groupActiveJobs(active: JobView[], dismissed: ReadonlySet<string>): ActiveJobGroups {
	const scanning = active.filter((j) => j.status?.toLowerCase() === 'created');
	const waiting = active.filter((j) => isWaiting(j, dismissed));
	const waitingIds = new Set(waiting.map((j) => j.id));
	const ripping = active.filter((j) => j.status?.toLowerCase() === 'ripping');
	// A job shown as a review card in Waiting does not also show in Finishing.
	const finishing = active.filter((j) => isAwaitingAction(j) && !waitingIds.has(j.id));
	return { scanning, waiting, ripping, finishing };
}
