// Display-only job status groups. Action gating (resolve / apply / abandon /
// delete) is NOT here: it comes from the backend on `job.actions`. Each map is
// keyed on the generated JobStatus so a new backend status fails `npm run check`
// until it is placed in every group.
import type { JobStatus, JobView } from '$lib/types/api.gen';
import type { LifecycleStageId } from '$lib/jobs/lifecycle-stage';
import { effectiveJobStatus } from '$lib/jobs/status';

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

// Raw statuses of a job whose disc has been ripped, in full or in part.
const RIPPED: Record<JobStatus, boolean> = {
	created: false,
	awaiting_user_id: false,
	identified: false,
	awaiting_review: false,
	ripping: false,
	ripped: true,
	ripped_partial: true,
	ripped_awaiting_identify: true,
	abandoned: false,
	failed: false
};

/**
 * The disc has been ripped: in full, in part, or still waiting on its
 * identity.
 */
export function isRipped(status: string): boolean {
	return RIPPED[status as JobStatus] === true;
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

const POST_RIP: Record<JobStatus, boolean> = {
	created: false,
	awaiting_user_id: false,
	identified: false,
	awaiting_review: false,
	ripping: false,
	ripped: true,
	ripped_partial: true,
	ripped_awaiting_identify: true,
	abandoned: false,
	failed: false
};

/** The rip has finished (the disc is post-rip, whatever happens next). */
export function isPostRipStatus(status: string): boolean {
	return POST_RIP[status as JobStatus] === true;
}

const REVIEW_CARD: Record<JobStatus, boolean> = {
	created: false,
	awaiting_user_id: true,
	identified: true,
	awaiting_review: true,
	ripping: false,
	ripped: false,
	ripped_partial: false,
	ripped_awaiting_identify: true,
	abandoned: false,
	failed: false
};

/**
 * Whether a raw status puts a job on the dashboard's review card.
 * `identified` is pre-rip (disc identified, waiting to start): it belongs on
 * the review card (with Start rip), NOT in FINISHING. Keeping it here keeps
 * the card up when applying a metadata match promotes a job to identified,
 * and after a page reload.
 */
export function isReviewCardStatus(status: string): boolean {
	return REVIEW_CARD[status.toLowerCase() as JobStatus] === true;
}
