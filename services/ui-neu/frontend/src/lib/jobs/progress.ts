// What a screen shows for a job's progress, from the job snapshot plus its
// live record. Every progress surface renders from jobProgress.
import type { IdentitySuggestion, JobView } from '$lib/types/api.gen';
import type { JobLive } from '$lib/stores/job-live.svelte';
import type { LiveSample } from '$lib/live/feeds';
import { effectiveJobStatus } from '$lib/jobs/status';
import { identitySuggestionOf, isIdentifyMiss, previouslyRippedJobId } from '$lib/jobs/review';
import { formatDuration } from '$lib/utils/format';

export type RailStage = 'identifying' | 'waiting' | 'ripping' | 'transcoding' | 'complete';
export type SegmentState = 'done' | 'active' | 'attention' | 'pending' | 'failed' | 'partial';
export type ReadoutTone = 'default' | 'success' | 'warning' | 'error';

export interface RailSegment {
	stage: RailStage;
	label: string;
	state: SegmentState;
	/** Fill percent for an active segment; null when unknown (it pulses). */
	pct: number | null;
}

export interface Readout {
	tone: ReadoutTone;
	label: string;
	detail: string | null;
	figure: string | null;
}

export interface JobProgressView {
	segments: RailSegment[];
	readout: Readout;
}

export interface ProgressContext {
	/** The clock, in ms, that the review countdown reads. */
	now: number;
	/** Config `manual_wait_seconds`: how long a review countdown runs. */
	reviewWaitSeconds: number;
	/** The global ripping pause (`!ripping_enabled`). */
	rippingPaused: boolean;
}

export type ProgressJob = Pick<
	JobView,
	| 'status'
	| 'rip_progress'
	| 'transcode_progress'
	| 'wait_start_time'
	| 'manual_pause'
	| 'episodes_unsure'
	| 'metadata_json'
	| 'title'
>;

const STAGES: { stage: RailStage; label: string }[] = [
	{ stage: 'identifying', label: 'ID' },
	{ stage: 'waiting', label: 'Wait' },
	{ stage: 'ripping', label: 'Rip' },
	{ stage: 'transcoding', label: 'Encode' },
	{ stage: 'complete', label: 'Done' }
];

/** One state per segment, in STAGES order; `pct` fills the active one. */
interface Position {
	states: SegmentState[];
	pct: number | null;
	readout: Readout;
}

const say = (
	label: string,
	detail: string | null = null,
	tone: ReadoutTone = 'default',
	figure: string | null = null
): Readout => ({ tone, label, detail, figure });

const finite = (n: number | null | undefined): number | null => (n != null && Number.isFinite(n) ? n : null);

function pctFigure(pct: number | null, eta: number | null): string | null {
	if (pct == null) return null;
	const p = `${Math.round(pct)}%`;
	return eta == null ? p : `${p} · ${formatDuration(eta, { coarse: true })} left`;
}

const COPY_STAGE_WORDS: Record<string, string> = {
	'scratch-to-media': 'Copying to shared storage',
	'work-to-completed': 'Moving to completed'
};

/**
 * The words for a rip's live progress stage: the two copy stages get plain
 * words and any other stage is shown as the ripper named it.
 */
export function ripStageWords(phase: string | null): string | null {
	if (phase == null) return null;
	return COPY_STAGE_WORDS[phase] ?? phase;
}

const row = (...states: SegmentState[]) => states;

// ---- rip, encode and the end states ----

function ripReadout(job: ProgressJob, live: JobLive, pct: number | null): Readout {
	const phase = live.rip?.phase ?? null;
	const rp = job.rip_progress;
	if (phase === 'verifying') return say('Verifying', 'checking the ripped files');
	if (!rp || rp.tracks_total === 0) return say('Ripping', 'starting MakeMKV');
	const n = Math.min(rp.current_track_index ?? rp.tracks_done + 1, rp.tracks_total);
	const figure = pctFigure(pct, finite(live.rip?.etaSeconds)) ?? `${rp.tracks_done} / ${rp.tracks_total} titles`;
	const detail = phase != null && phase in COPY_STAGE_WORDS ? ripStageWords(phase) : `title ${n} of ${rp.tracks_total}`;
	return say('Ripping', detail, 'default', figure);
}

function ripping(job: ProgressJob, live: JobLive): Position {
	const pct = finite(live.rip?.pct);
	return { states: row('done', 'done', 'active', 'pending', 'pending'), pct, readout: ripReadout(job, live, pct) };
}

function transcoding(job: ProgressJob, live: JobLive): Position {
	const tp = job.transcode_progress;
	const pct = finite(live.transcode?.pct) ?? finite(tp?.percent) ?? null;
	const detail = tp
		? `task ${Math.min(tp.tasks_done + tp.tasks_failed + 1, tp.tasks_total)} of ${tp.tasks_total}`
		: null;
	const figure = pctFigure(pct, finite(live.transcode?.etaSeconds));
	return {
		states: row('done', 'done', 'done', 'active', 'pending'),
		pct,
		readout: say('Transcoding', detail, 'default', figure)
	};
}

function transcodeFailed(job: ProgressJob): Position {
	const tp = job.transcode_progress;
	if (tp?.state === 'done_partial') {
		return {
			states: row('done', 'done', 'done', 'done', 'partial'),
			pct: null,
			readout: say('Done with gaps', `${tp.tasks_done} of ${tp.tasks_total} tasks succeeded`, 'warning')
		};
	}
	return {
		states: row('done', 'done', 'done', 'failed', 'pending'),
		pct: null,
		readout: say('Failed during encode', null, 'error')
	};
}

function failedLabel(abandoned: boolean, ripStarted: boolean): string {
	if (abandoned) return 'Abandoned';
	return ripStarted ? 'Failed during rip' : 'Failed';
}

/**
 * The job records no failure stage (issue #625), and the backend sends
 * rip_progress only while ripping. Started tracks in rip_progress place the
 * failure in RIP; otherwise the stage is unknown, so the readout says only
 * "Failed" and the ID segment, the one position left, carries the failure.
 */
function failed(job: ProgressJob, abandoned: boolean): Position {
	const ripStarted = (job.rip_progress?.tracks_total ?? 0) > 0;
	return {
		states: ripStarted
			? row('done', 'done', 'failed', 'pending', 'pending')
			: row('failed', 'pending', 'pending', 'pending', 'pending'),
		pct: null,
		readout: say(failedLabel(abandoned, ripStarted), null, 'error')
	};
}

function complete(job: ProgressJob): Position {
	const n = job.rip_progress?.tracks_total ?? 0;
	return {
		states: row('done', 'done', 'done', 'done', 'done'),
		pct: null,
		readout: say('Complete', n > 0 ? `${n} ${n === 1 ? 'track' : 'tracks'}` : null, 'success')
	};
}

// ---- before the rip ----

type ReviewCase = 'suggestion' | 'previous' | 'unsure' | 'paused' | 'countdown';

/** Which of the five awaiting_review cases the job is in, checked in the backend's hold order. */
function reviewCase(job: ProgressJob, ctx: ProgressContext): ReviewCase {
	if (identitySuggestionOf(job)) return 'suggestion';
	if (previouslyRippedJobId(job)) return 'previous';
	if (job.episodes_unsure) return 'unsure';
	if (job.manual_pause || ctx.rippingPaused || job.wait_start_time == null) return 'paused';
	return 'countdown';
}

/** True while the review countdown is running; the rail ticks only then. */
export function isCountingDown(job: ProgressJob, ctx: ProgressContext): boolean {
	return effectiveJobStatus(job) === 'awaiting_review' && reviewCase(job, ctx) === 'countdown';
}

/** Seconds since the countdown began (only called with a wait_start_time set); an unreadable or future start counts as none. */
function secondsWaited(job: ProgressJob, ctx: ProgressContext): number {
	const elapsed = (ctx.now - Date.parse(String(job.wait_start_time))) / 1000;
	return Number.isFinite(elapsed) ? Math.max(0, elapsed) : 0;
}

function countdown(job: ProgressJob, ctx: ProgressContext): Position {
	const length = ctx.reviewWaitSeconds;
	const elapsed = secondsWaited(job, ctx);
	const overdue = length <= 0 || elapsed >= length;
	const pct = overdue ? 100 : (elapsed / length) * 100;
	const readout = overdue
		? say('Starting', 'waiting for the ripper')
		: say('Waiting for review', `starts in ${formatDuration(length - elapsed, { coarse: true })}`);
	return { states: row('done', 'active', 'pending', 'pending', 'pending'), pct, readout };
}

const heldAt = (readout: Readout): Position => ({
	states: row('done', 'attention', 'pending', 'pending', 'pending'),
	pct: null,
	readout
});

function awaitingReview(job: ProgressJob, ctx: ProgressContext): Position {
	switch (reviewCase(job, ctx)) {
		case 'suggestion':
			return {
				states: row('attention', 'pending', 'pending', 'pending', 'pending'),
				pct: null,
				readout: say('Confirm the match', (identitySuggestionOf(job) as IdentitySuggestion).title)
			};
		case 'previous':
			return heldAt(say('Ripped before', 'rip again or discard'));
		case 'unsure':
			return heldAt(say('Held', 'episodes are a guess'));
		case 'paused':
			return heldAt(say('Paused', 'countdown paused'));
		default:
			return countdown(job, ctx);
	}
}

const at = (states: SegmentState[], label: string, detail: string | null = null): Position => ({
	states,
	pct: null,
	readout: say(label, detail)
});

type Builder = (job: ProgressJob, live: JobLive, ctx: ProgressContext) => Position;

// Each effective status's position: a builder for the ones that read data, a fixed one otherwise.
const POSITION: Record<string, Builder> = {
	created: () => at(row('active', 'pending', 'pending', 'pending', 'pending'), 'Identifying', 'looking up the disc'),
	awaiting_user_id: () =>
		at(row('attention', 'pending', 'pending', 'pending', 'pending'), 'Waiting for identification'),
	awaiting_review: (job, _live, ctx) => awaitingReview(job, ctx),
	identified: () => at(row('done', 'done', 'active', 'pending', 'pending'), 'Queued to rip', 'waiting for the drive'),
	ripping,
	ripped: () => at(row('done', 'done', 'done', 'attention', 'pending'), 'Ripped', 'waiting for a session'),
	ripped_partial: () =>
		at(row('done', 'done', 'done', 'attention', 'pending'), 'Ripped with gaps', 'waiting for a session'),
	ripped_awaiting_identify: () =>
		at(row('attention', 'done', 'done', 'pending', 'pending'), 'Ripped', 'waiting for identification'),
	transcoding,
	transcode_failed: (job) => transcodeFailed(job),
	complete: (job) => complete(job),
	failed: (job) => failed(job, false),
	abandoned: (job) => failed(job, true)
};

const UNKNOWN: Position = at(row('pending', 'pending', 'pending', 'pending', 'pending'), 'Waiting');

const OVERLAY_STATUSES = new Set(['identified', 'ripping']);

/** A job that rips without an identity shows ID as owed, with "no identity" in the detail. */
function withIdentityOwed(job: ProgressJob, status: string, pos: Position): Position {
	if (!OVERLAY_STATUSES.has(status) || !isIdentifyMiss(job)) return pos;
	const detail = [pos.readout.detail, 'no identity'].filter(Boolean).join(', ');
	return {
		...pos,
		states: ['attention', ...pos.states.slice(1)],
		readout: { ...pos.readout, detail }
	};
}

function segmentsFor(pos: Position): RailSegment[] {
	const activeAt = pos.states.indexOf('active');
	return STAGES.map((s, i) => ({ ...s, state: pos.states[i], pct: i === activeAt ? pos.pct : null }));
}

export function jobProgress(job: ProgressJob, live: JobLive, ctx: ProgressContext): JobProgressView {
	const status = effectiveJobStatus(job);
	const build = POSITION[status];
	const pos = withIdentityOwed(job, status, build ? build(job, live, ctx) : UNKNOWN);
	return { segments: segmentsFor(pos), readout: pos.readout };
}

const NO_SAMPLE: LiveSample = {
	pct: null,
	etaSeconds: null,
	fps: null,
	avgFps: null,
	pass: null,
	bytesDone: null,
	bytesTotal: null,
	rateBps: null,
	phase: null,
	trackId: null
};

/**
 * The live sample a progress line draws: the rip's, else the transcode's. A
 * transcoding job with no live percent shows its snapshot percent, the same
 * fallback the stage rail uses.
 */
export function progressSample(job: ProgressJob, live: JobLive): LiveSample | null {
	if (live.rip) return live.rip;
	const snapshot = finite(job.transcode_progress?.percent);
	const livePctMissing = finite(live.transcode?.pct) == null;
	if (snapshot == null || !livePctMissing || effectiveJobStatus(job) !== 'transcoding') return live.transcode;
	return { ...NO_SAMPLE, ...live.transcode, pct: snapshot };
}
