// One-line summary of the sessions parked on a job.
import type { JobView } from '$lib/types/api.gen';
import { isPostRipStatus } from '$lib/jobs/status-groups';

function shortSessionId(id: string): string {
	return id.length > 15 ? `${id.slice(0, 15)}...` : id;
}

/** A session's name, else its id shortened. */
export function sessionDisplayName(id: string, names: Map<string, string>): string {
	return names.get(id) ?? shortSessionId(id);
}

function parkedSuffix(status: JobView['status']): string {
	if (status === 'failed') return 'not applied, the rip failed';
	if (status === 'abandoned') return 'not applied, the job was abandoned';
	return isPostRipStatus(status) ? 'waiting' : 'applies when the rip finishes';
}

/**
 * "Name[, Name], applies when the rip finishes" pre-rip, "..., waiting" post-rip,
 * "..., not applied, ..." once the rip failed or the job was abandoned; null if none parked.
 */
export function parkedSessionLine(
	job: Pick<JobView, 'parked_session_ids' | 'status'>,
	names: Map<string, string>
): string | null {
	const ids = job.parked_session_ids ?? [];
	if (ids.length === 0) return null;
	const label = ids.map((id) => sessionDisplayName(id, names)).join(', ');
	return `${label}, ${parkedSuffix(job.status)}`;
}
