import type { IdentitySuggestion, JobView } from '$lib/types/api.gen';

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
				return 'complete';
			// A partially- or fully-FAILED transcode is NOT "complete" — the disc
			// ripped fine but some/all tracks failed to transcode. Surface that
			// honestly as a transcode failure (the lifecycle stepper paints the
			// transcode stage red; the rip stage stays done). `isPartialComplete`
			// still adds the "Done x/y" chip so partial-vs-total stays visible.
			case 'done_partial':
			case 'failed':
				return 'transcode_failed';
		}
	}
	return s;
}

/** True when the job finished transcoding but some titles failed. */
export function isPartialComplete(job: JobLike): boolean {
	return job.transcode_progress?.state === 'done_partial';
}

const RIPPING_STATUSES = new Set(['ripping']);

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

type BadgeJob = Pick<JobView, 'status' | 'title' | 'transcode_progress'> & {
	metadata_json?: JobView['metadata_json'];
};

/**
 * The earlier rip a held disc matched (on_previously_ripped = hold), or null.
 * A job held for this reason has no countdown: it waits for Rip again or
 * Discard.
 */
export function previouslyRippedJobId(
	job: { metadata_json?: JobView['metadata_json'] } | null | undefined
): string | null {
	const id = job?.metadata_json?.previously_ripped?.job_id;
	return typeof id === 'string' && id ? id : null;
}

/**
 * The confident match identify held for confirmation (the media type's
 * auto-apply switch is off), or null. Accepting it applies the title.
 */
export function identitySuggestionOf(
	job: { metadata_json?: JobView['metadata_json'] } | null | undefined
): IdentitySuggestion | null {
	return job?.metadata_json?.identity_suggestion ?? null;
}

type MissAttempt = { source?: unknown; step?: unknown; outcome?: unknown; detail?: unknown };

/**
 * One line saying why identify's automatic match missed, from the attempts
 * it stored (`metadata_json.identify_attempts`), or null: the job is not a
 * miss (neither `flags.unidentified` nor awaiting_user_id), or it has no
 * attempts (jobs identified before the list existed).
 */
export function missReason(
	job: Pick<JobView, 'status' | 'title'> & { metadata_json?: JobView['metadata_json'] }
): string | null {
	const meta = job.metadata_json;
	if (job.status !== 'awaiting_user_id' && meta?.flags?.unidentified !== true) return null;
	const attempts = (meta?.identify_attempts ?? []) as MissAttempt[];
	if (attempts.length === 0) return null;
	const outcomes = attempts.map((a) => a.outcome);
	if (outcomes.includes('no_sources')) return 'No online source is switched on for this kind of disc.';
	if (outcomes.every((o) => o === 'not_configured')) return 'No API keys are saved for the sources in your lists.';
	if (outcomes.includes('timeout') && !outcomes.includes('miss')) return 'The lookup timed out. Try the search below.';
	// The searched title: the last title search that names one. The
	// whole-dispatch timeout entry (no source) carries a message, not a title.
	const searched = attempts.findLast(
		(a) => a.step === 'title' && a.source != null && typeof a.detail === 'string' && a.detail
	)?.detail as string | undefined;
	const title = searched || job.title?.trim() || 'this disc';
	return `No source found a close match for "${title}". Try another source in the search below.`;
}

/** Display names for identification provider ids. */
export const PROVIDER_LABELS: Record<string, string> = {
	tmdb: 'TMDb',
	omdb: 'OMDb',
	tvmaze: 'TVmaze',
	tvdb: 'TVDB',
	musicbrainz: 'MusicBrainz',
	arm_server: 'ARM community database',
	thediscdb: 'TheDiscDB'
};

/** A provider id's display name; an unknown id shows as itself. */
export function providerLabel(provider: string): string {
	return PROVIDER_LABELS[provider] ?? provider;
}

const CONFIRM_TITLE_STATUSES = new Set(['awaiting_review', 'awaiting_user_id', 'ripped_awaiting_identify']);

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
	if (s === 'awaiting_review' && previouslyRippedJobId(job))
		return { label: 'ALREADY RIPPED', accent: 'var(--color-accent-4)' };
	if (CONFIRM_TITLE_STATUSES.has(s) && identitySuggestionOf(job))
		return { label: 'CONFIRM TITLE', accent: 'var(--color-accent-4)' };
	if (s === 'awaiting_review') return { label: 'REVIEW', accent: 'var(--color-accent-1)' };
	if (s === 'awaiting_user_id' || s === 'ripped_awaiting_identify')
		return { label: 'IDENTIFY', accent: 'var(--color-accent-4)' };
	if (s === 'identified') return { label: 'READY', accent: 'var(--color-primary)' };
	if (s === 'ripped' || s === 'ripped_partial')
		return { label: 'RIPPED | NEEDS SESSION', accent: 'var(--color-accent-3)' };
	return { label: s.toUpperCase(), accent: 'var(--color-primary)' };
}

/**
 * The jobs-table Transcode column display for a job, gated so it is only
 * "Complete" (green) when every task succeeded. A retry-in-flight on a session
 * that already has failures reads red ("Failed — retrying"), never hopeful blue.
 * Returns null when no session has been applied (render an em-dash).
 */
export function transcodeColumnStatus(
	job: Pick<JobView, 'transcode_progress'>
): { label: string; badgeStatus: string } | null {
	const tp = job.transcode_progress;
	if (tp == null) return null;
	const { tasks_done, tasks_total, tasks_failed } = tp;
	switch (tp.state) {
		case 'done':
			return { label: 'Complete', badgeStatus: 'complete' };
		case 'done_partial':
		case 'failed':
			return { label: 'Transcode failed', badgeStatus: 'transcode_failed' };
		case 'transcoding':
			return tasks_failed > 0
				? { label: `Failed, retrying ${tasks_done}/${tasks_total}`, badgeStatus: 'transcode_failed' }
				: { label: `Transcoding ${tasks_done}/${tasks_total}`, badgeStatus: 'transcoding' };
		default:
			return null;
	}
}
