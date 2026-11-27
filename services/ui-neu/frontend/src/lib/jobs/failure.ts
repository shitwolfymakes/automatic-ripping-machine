// What a failed job tells the operator about why it failed.
import type { JobView } from '$lib/types/api.gen';

/** The sentence explaining why the job failed, or null when it has none to show. */
export function failureReasonOf(job: Pick<JobView, 'failure_reason'> | null | undefined): string | null {
	const reason = job?.failure_reason?.trim();
	return reason ? reason : null;
}
