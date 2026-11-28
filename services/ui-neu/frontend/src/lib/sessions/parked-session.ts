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

// A ripped job's parked session waits on transcoding, which only these
// statuses resume when it is switched back on; ripped_awaiting_identify waits on identity.
const RESUMES_WITH_TRANSCODING: ReadonlySet<JobView['status']> = new Set(['ripped', 'ripped_partial']);

/**
 * "Name[, Name], applies when the rip finishes" pre-rip, "..., waiting" post-rip,
 * "...: Transcoding is currently unavailable. ..." post-rip with transcoding off,
 * "..., not applied, ..." once the rip failed or the job was abandoned; null if none parked.
 */
export function parkedSessionLine(
	job: Pick<JobView, 'parked_session_ids' | 'status'>,
	names: Map<string, string>,
	transcodeEnabled = true
): string | null {
	const ids = job.parked_session_ids ?? [];
	if (ids.length === 0) return null;
	const label = ids.map((id) => sessionDisplayName(id, names)).join(', ');
	if (!transcodeEnabled && RESUMES_WITH_TRANSCODING.has(job.status)) {
		return `${label}: Transcoding is currently unavailable. Please enable to resume.`;
	}
	return `${label}, ${parkedSuffix(job.status)}`;
}
