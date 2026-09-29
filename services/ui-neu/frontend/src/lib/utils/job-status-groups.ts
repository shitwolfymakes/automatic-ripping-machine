// Display-only job status groups. Action gating (resolve / apply / abandon /
// delete) is NOT here: it comes from the backend on `job.actions`. Each map is
// keyed on the generated JobStatus so a new backend status fails `npm run check`
// until it is placed in every group.
import type { JobStatus, JobView } from '$lib/types/api.gen';
import type { LifecycleStageId } from '$lib/utils/job-lifecycle';
import { effectiveJobStatus } from '$lib/utils/job-status';

// Raw statuses after which nothing further happens to the job.
const FINAL: Record<JobStatus, boolean> = {
	created: false,
	awaiting_user_id: false,
	identified: false,
	awaiting_review: false,
	ripping: false,
	ripped: false,
	ripped_partial: false,
	ripped_awaiting_identify: false,
	abandoned: true,
	failed: true
};

// Effective (display) statuses that end a post-rip job's transcode phase.
const TRANSCODE_FINISHED = new Set(['complete', 'transcode_failed']);

/** Whether a job can still change on its own: keep polling / streaming logs. */
export function isLive(job: Pick<JobView, 'status' | 'transcode_progress'>): boolean {
	const raw = job.status?.toLowerCase() as JobStatus;
	if (FINAL[raw] === true) return false;
	return !TRANSCODE_FINISHED.has(effectiveJobStatus(job));
}

// Post-rip statuses where the job sits idle until the operator acts
// (apply a session / identify). Live (may still change) but not in progress.
const IDLE_EFFECTIVE = new Set(['ripped', 'ripped_partial', 'ripped_awaiting_identify']);

/** Work is actively happening (card stepper / shimmer). */
export function isInProgress(job: Pick<JobView, 'status' | 'transcode_progress'>): boolean {
	return isLive(job) && !IDLE_EFFECTIVE.has(effectiveJobStatus(job));
}

const AWAITING_IDENTITY: Record<JobStatus, boolean> = {
	created: false,
	awaiting_user_id: true,
	identified: false,
	awaiting_review: false,
	ripping: false,
	ripped: false,
	ripped_partial: false,
	ripped_awaiting_identify: true,
	abandoned: false,
	failed: false
};

/** Identification failed and the operator must supply it ("Identify disc" vs "Edit identity"). */
export function isAwaitingIdentity(status: string): boolean {
	return AWAITING_IDENTITY[status as JobStatus] === true;
}

const STAGE_BY_STATUS: Record<JobStatus, LifecycleStageId | null> = {
	created: 'identifying',
	awaiting_user_id: 'identifying',
	identified: 'identifying',
	awaiting_review: 'identifying',
	ripping: 'ripping',
	ripped: 'ripping',
	ripped_partial: 'ripping',
	ripped_awaiting_identify: 'ripping',
	abandoned: null,
	failed: null
};

const STAGE_BY_EFFECTIVE: Record<string, LifecycleStageId> = {
	transcoding: 'transcoding',
	complete: 'complete'
};

export const LIFECYCLE_FAILURE_STATUSES: ReadonlySet<string> = new Set(['failed', 'abandoned', 'transcode_failed']);

/** Lifecycle stage for a raw or effective status; null for failures and unknowns. */
export function lifecycleStageFor(status: string): LifecycleStageId | null {
	const s = status.toLowerCase();
	return STAGE_BY_EFFECTIVE[s] ?? STAGE_BY_STATUS[s as JobStatus] ?? null;
}
