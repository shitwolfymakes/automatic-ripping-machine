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

const FINISHING_RAW = new Set(['identified', 'ripped', 'ripped_partial']);

/**
 * A job belongs in the dashboard's FINISHING ("awaiting action") section when
 * the rip is done/identified but NO transcode session is in flight or complete
 * — i.e. it needs the operator to apply a session. A transcoding or completed
 * job leaves FINISHING (it shows transcode state / drops to All Jobs).
 */
export function isAwaitingAction(job: JobLike): boolean {
	const s = job.status?.toLowerCase() ?? '';
	if (!FINISHING_RAW.has(s)) return false;
	const eff = effectiveJobStatus(job);
	return eff === 'ripped' || eff === 'ripped_partial' || eff === 'identified';
}
