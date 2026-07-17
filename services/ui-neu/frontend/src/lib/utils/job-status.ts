import type { JobView } from '$lib/types/api.gen';

type JobLike = Pick<JobView, 'status' | 'transcode_progress'>;

const POST_RIP = new Set(['ripped', 'ripped_partial']);

/**
 * Fold a job's raw status + its transcode_progress summary into a single
 * display status. A post-rip job (`ripped`/`ripped_partial`) with an applied
 * session reflects the session's rollup: transcoding while in-flight, then
 * complete / failed. With no session applied it stays `ripped` (awaiting
 * action). All other statuses pass through unchanged.
 */
export function effectiveJobStatus(job: JobLike): string {
	const s = job.status?.toLowerCase() ?? '';
	const tp = job.transcode_progress;
	if (POST_RIP.has(s) && tp != null) {
		switch (tp.state) {
			case 'transcoding':
				return 'transcoding';
			case 'done':
			case 'done_partial':
				return 'complete';
			case 'failed':
				return 'failed';
		}
	}
	return s;
}

/** True when the job finished transcoding but some titles failed. */
export function isPartialComplete(job: JobLike): boolean {
	return job.transcode_progress?.state === 'done_partial';
}

const RIPPING_STATUSES = new Set(['ripping', 'video_ripping', 'audio_ripping', 'importing', 'copying', 'ejecting']);

/** Count jobs that are genuinely in the disc-rip phase (header "N ripping"). */
export function countRipping(jobs: JobLike[]): number {
	return jobs.filter((j) => RIPPING_STATUSES.has(effectiveJobStatus(j))).length;
}

// FINISHING is the POST-rip "awaiting a transcode session" bucket. `identified`
// is PRE-rip (disc identified, waiting to start) — it belongs on the review card,
// not here — so it is deliberately excluded.
const FINISHING_RAW = new Set(['ripped', 'ripped_partial']);

/**
 * A job belongs in the dashboard's FINISHING ("awaiting action") section when
 * the rip is done but NO transcode session is in flight or complete — i.e. it
 * needs the operator to apply a session. A transcoding or completed job leaves
 * FINISHING (it shows transcode state / drops to All Jobs). Pre-rip `identified`
 * jobs are NOT finishing — they show the review card.
 */
export function isAwaitingAction(job: JobLike): boolean {
	const s = job.status?.toLowerCase() ?? '';
	if (!FINISHING_RAW.has(s)) return false;
	const eff = effectiveJobStatus(job);
	return eff === 'ripped' || eff === 'ripped_partial';
}

/** True when the job carries a non-empty, non-whitespace title. */
export function hasTitleMatch(job: Pick<JobView, 'title'>): boolean {
	return typeof job.title === 'string' && job.title.trim().length > 0;
}

type BadgeJob = Pick<JobView, 'status' | 'title' | 'transcode_progress'>;

/**
 * The header phase pill for any job rendered as a review card. Pre-rip statuses
 * map to REVIEW / IDENTIFY / READY; a post-rip job awaiting a session reads
 * RIPPED · NEEDS SESSION (or · NEEDS TITLE when a session is somehow present but
 * the title is missing — session is the hard transcode blocker, so it wins when
 * both are missing). Accent uses the same `var(--token, #hex)` fallback idiom as
 * the dashboard section frames; `--color-violet-500` is undefined so its #hex is
 * authoritative.
 */
export function reviewPhaseBadge(job: BadgeJob): { label: string; accent: string } {
	const s = job.status?.toLowerCase() ?? '';
	if (s === 'awaiting_review') return { label: 'REVIEW', accent: 'var(--color-amber-500, #f59e0b)' };
	if (s === 'awaiting_user_id' || s === 'ripped_awaiting_identify')
		return { label: 'IDENTIFY', accent: 'var(--color-cyan-500, #06b6d4)' };
	if (s === 'identified') return { label: 'READY', accent: 'var(--color-primary)' };
	if (s === 'ripped' || s === 'ripped_partial')
		return { label: 'RIPPED · NEEDS SESSION', accent: 'var(--color-violet-500, #8b5cf6)' };
	return { label: s.toUpperCase(), accent: 'var(--color-primary)' };
}
