import { describe, it, expect } from 'vitest';
import {
	jobProgress,
	isCountingDown,
	progressSample,
	ripStageWords,
	type ProgressJob,
	type ProgressContext
} from '../progress';
import { EMPTY_LIVE, type JobLive } from '$lib/stores/job-live.svelte';
import type { LiveSample } from '$lib/live/feeds';

const T0 = Date.parse('2026-01-01T00:00:00Z');
const CTX: ProgressContext = { now: T0 + 30_000, reviewWaitSeconds: 120, rippingPaused: false };

const job = (over: Record<string, unknown> = {}): ProgressJob =>
	({
		status: 'created',
		rip_progress: null,
		transcode_progress: null,
		wait_start_time: null,
		manual_pause: false,
		episodes_unsure: false,
		metadata_json: null,
		title: null,
		...over
	}) as unknown as ProgressJob;

const sample = (over: Partial<LiveSample> = {}): LiveSample => ({
	pct: null,
	etaSeconds: null,
	fps: null,
	avgFps: null,
	pass: null,
	bytesDone: null,
	bytesTotal: null,
	rateBps: null,
	phase: null,
	trackId: null,
	...over
});

const ripLive = (over: Partial<LiveSample> = {}): JobLive => ({ rip: sample(over), transcode: null });
const encLive = (over: Partial<LiveSample> = {}): JobLive => ({
	rip: null,
	transcode: { ...sample(over), taskId: 't1' }
});

const rp = (over: Record<string, unknown> = {}) => ({
	tracks_total: 4,
	tracks_done: 1,
	tracks_failed: 0,
	current_track_id: null,
	current_track_index: null,
	...over
});
const tp = (over: Record<string, unknown> = {}) => ({
	state: 'transcoding',
	tasks_total: 3,
	tasks_done: 1,
	tasks_failed: 0,
	percent: 10,
	...over
});

const states = (j: ProgressJob, live: JobLive = EMPTY_LIVE, ctx = CTX) =>
	jobProgress(j, live, ctx).segments.map((s) => s.state);
const readout = (j: ProgressJob, live: JobLive = EMPTY_LIVE, ctx = CTX) => jobProgress(j, live, ctx).readout;

const waiting = (over: Record<string, unknown> = {}) =>
	job({ status: 'awaiting_review', wait_start_time: '2026-01-01T00:00:00Z', ...over });

describe('jobProgress: segment order', () => {
	it('lists ID, Wait, Rip, Encode, Done', () => {
		const v = jobProgress(job(), EMPTY_LIVE, CTX);
		expect(v.segments.map((s) => s.stage)).toEqual(['identifying', 'waiting', 'ripping', 'transcoding', 'complete']);
		expect(v.segments.map((s) => s.label)).toEqual(['ID', 'Wait', 'Rip', 'Encode', 'Done']);
	});
});

describe('jobProgress: status table', () => {
	it('created', () => {
		expect(states(job())).toEqual(['active', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(job())).toEqual({
			tone: 'default',
			label: 'Identifying',
			detail: 'looking up the disc',
			figure: null
		});
	});
	it('awaiting_user_id', () => {
		const j = job({ status: 'awaiting_user_id' });
		expect(states(j)).toEqual(['attention', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'default', label: 'Waiting for identification', detail: null, figure: null });
	});
	it('awaiting_review: suggestion', () => {
		const j = waiting({ metadata_json: { identity_suggestion: { provider: 'tmdb', title: 'Heat' } } });
		expect(states(j)).toEqual(['attention', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'default', label: 'Confirm the match', detail: 'Heat', figure: null });
	});
	it('awaiting_review: a shortlist asks for a pick', () => {
		const alternatives = [{ title: 'Total Recall' }, { title: 'Total Recall' }];
		const j = waiting({
			metadata_json: { identity_suggestion: { reason: 'close', provider: 'tmdb', title: 'Total Recall', alternatives } }
		});
		expect(readout(j)).toEqual({ tone: 'default', label: 'Pick the match', detail: '2 close titles', figure: null });
	});
	it('awaiting_review: previously ripped', () => {
		const j = waiting({ metadata_json: { previously_ripped: { job_id: 'j0' } } });
		expect(states(j)).toEqual(['done', 'attention', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({
			tone: 'default',
			label: 'Ripped before',
			detail: 'rip again or discard',
			figure: null
		});
	});
	it('awaiting_review: episodes unsure', () => {
		const j = waiting({ episodes_unsure: true });
		expect(states(j)).toEqual(['done', 'attention', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'default', label: 'Held', detail: 'episodes are a guess', figure: null });
	});
	it('awaiting_review: paused', () => {
		const j = waiting({ manual_pause: true });
		expect(states(j)).toEqual(['done', 'attention', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'default', label: 'Paused', detail: 'countdown paused', figure: null });
	});
	it('awaiting_review: countdown', () => {
		const j = waiting();
		expect(states(j)).toEqual(['done', 'active', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({
			tone: 'default',
			label: 'Waiting for review',
			detail: 'starts in 1m 30s',
			figure: null
		});
	});
	it('identified', () => {
		const j = job({ status: 'identified' });
		expect(states(j)).toEqual(['done', 'done', 'active', 'pending', 'pending']);
		expect(readout(j)).toEqual({
			tone: 'default',
			label: 'Queued to rip',
			detail: 'waiting for the drive',
			figure: null
		});
		expect(jobProgress(j, EMPTY_LIVE, CTX).segments[2].pct).toBeNull();
	});
	it('ripping with a live tick', () => {
		const j = job({ status: 'ripping', rip_progress: rp({ current_track_index: 2 }) });
		const v = jobProgress(j, ripLive({ pct: 42.4, etaSeconds: 1080 }), CTX);
		expect(v.segments.map((s) => s.state)).toEqual(['done', 'done', 'active', 'pending', 'pending']);
		expect(v.segments[2].pct).toBe(42.4);
		expect(v.readout).toEqual({ tone: 'default', label: 'Ripping', detail: 'title 2 of 4', figure: '42% | 18m left' });
	});
	it('ripping with a percent and no ETA', () => {
		const j = job({ status: 'ripping', rip_progress: rp() });
		expect(readout(j, ripLive({ pct: 10 })).figure).toBe('10%');
	});
	it('ripping before the first tick shows titles done', () => {
		const j = job({ status: 'ripping', rip_progress: rp({ current_track_index: null }) });
		expect(readout(j)).toEqual({ tone: 'default', label: 'Ripping', detail: 'title 2 of 4', figure: '1 / 4 titles' });
	});
	it('ripping with no track counts says starting MakeMKV', () => {
		for (const rip_progress of [null, rp({ tracks_total: 0 })]) {
			const j = job({ status: 'ripping', rip_progress });
			expect(readout(j)).toEqual({ tone: 'default', label: 'Ripping', detail: 'starting MakeMKV', figure: null });
		}
	});
	it('ripping in a copy stage uses its words', () => {
		const j = job({ status: 'ripping', rip_progress: rp({ current_track_index: 1 }) });
		const r = readout(j, ripLive({ phase: 'scratch-to-media' }));
		expect(r.label).toBe('Ripping');
		expect(r.detail).toBe('Copying to shared storage');
	});
	it('ripped and ripped_partial', () => {
		expect(states(job({ status: 'ripped' }))).toEqual(['done', 'done', 'done', 'attention', 'pending']);
		expect(readout(job({ status: 'ripped' }))).toEqual({
			tone: 'default',
			label: 'Ripped',
			detail: 'waiting for a session',
			figure: null
		});
		expect(states(job({ status: 'ripped_partial' }))).toEqual(['done', 'done', 'done', 'attention', 'pending']);
		expect(readout(job({ status: 'ripped_partial' })).label).toBe('Ripped with gaps');
	});
	it('ripped_awaiting_identify', () => {
		const j = job({ status: 'ripped_awaiting_identify' });
		expect(states(j)).toEqual(['attention', 'done', 'done', 'pending', 'pending']);
		expect(readout(j)).toEqual({
			tone: 'default',
			label: 'Ripped',
			detail: 'waiting for identification',
			figure: null
		});
	});
	it('transcoding takes the live percent and ETA', () => {
		const j = job({ status: 'ripped', transcode_progress: tp() });
		const v = jobProgress(j, encLive({ pct: 55, etaSeconds: 600 }), CTX);
		expect(v.segments.map((s) => s.state)).toEqual(['done', 'done', 'done', 'active', 'pending']);
		expect(v.segments[3].pct).toBe(55);
		expect(v.readout).toEqual({
			tone: 'default',
			label: 'Transcoding',
			detail: 'task 2 of 3',
			figure: '55% | 10m left'
		});
	});
	it('transcoding falls back to the snapshot percent', () => {
		const j = job({ status: 'ripped', transcode_progress: tp({ percent: 10, tasks_done: 3 }) });
		const v = jobProgress(j, EMPTY_LIVE, CTX);
		expect(v.segments[3].pct).toBe(10);
		expect(v.readout.detail).toBe('task 3 of 3');
		expect(v.readout.figure).toBe('10%');
	});
	it('transcoding with no snapshot at all', () => {
		const j = job({ status: 'transcoding' });
		expect(readout(j)).toEqual({ tone: 'default', label: 'Transcoding', detail: null, figure: null });
	});
	it('complete', () => {
		const j = job({ status: 'ripped', transcode_progress: tp({ state: 'done' }) });
		expect(states(j)).toEqual(['done', 'done', 'done', 'done', 'done']);
		expect(readout(j)).toEqual({ tone: 'success', label: 'Complete', detail: null, figure: null });
	});
	it('complete shows the track count only when rip_progress is present', () => {
		const j = job({ status: 'ripped', transcode_progress: tp({ state: 'done' }), rip_progress: rp() });
		expect(readout(j).detail).toBe('4 tracks');
	});
	it('complete with no track count has no detail', () => {
		const j = job({ status: 'complete' });
		expect(readout(j).detail).toBeNull();
	});
	it('transcode_failed, partly done', () => {
		const j = job({
			status: 'ripped',
			transcode_progress: tp({ state: 'done_partial', tasks_done: 2, tasks_failed: 1 })
		});
		expect(states(j)).toEqual(['done', 'done', 'done', 'done', 'partial']);
		expect(readout(j)).toEqual({
			tone: 'warning',
			label: 'Done with gaps',
			detail: '2 of 3 tasks succeeded',
			figure: null
		});
	});
	it('caps the title number at the total', () => {
		const j = job({ status: 'ripping', rip_progress: rp({ tracks_done: 4 }) });
		expect(readout(j).detail).toBe('title 4 of 4');
	});
	it('counts a failed task toward the task number', () => {
		const j = job({ status: 'transcoding', transcode_progress: tp({ tasks_done: 1, tasks_failed: 1 }) });
		expect(readout(j).detail).toBe('task 3 of 3');
	});
	it('a non-finite live percent falls back to the snapshot percent', () => {
		const j = job({ status: 'transcoding', transcode_progress: tp({ percent: 30 }) });
		expect(jobProgress(j, encLive({ pct: NaN }), CTX).segments[3].pct).toBe(30);
	});
	it('complete with one track reads singular', () => {
		const j = job({ status: 'complete', rip_progress: rp({ tracks_total: 1 }) });
		expect(readout(j).detail).toBe('1 track');
	});
	it('transcode_failed, all failed', () => {
		const j = job({ status: 'ripped', transcode_progress: tp({ state: 'failed', tasks_failed: 3 }) });
		expect(states(j)).toEqual(['done', 'done', 'done', 'failed', 'pending']);
		expect(readout(j)).toEqual({ tone: 'error', label: 'Failed during encode', detail: null, figure: null });
	});
	it('transcode_failed with no snapshot is still a failed encode', () => {
		const j = job({ status: 'transcode_failed' });
		expect(states(j)).toEqual(['done', 'done', 'done', 'failed', 'pending']);
	});
	it('failed with started tracks in rip_progress places the failure in RIP', () => {
		const j = job({ status: 'failed', rip_progress: rp() });
		expect(states(j)).toEqual(['done', 'done', 'failed', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'error', label: 'Failed during rip', detail: null, figure: null });
	});
	it('failed without rip_progress (the backend sends none outside ripping) names no stage', () => {
		const j = job({ status: 'failed' });
		expect(states(j)).toEqual(['failed', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'error', label: 'Failed', detail: null, figure: null });
	});
	it('failed with an empty rip_progress names no stage', () => {
		const j = job({ status: 'failed', rip_progress: rp({ tracks_total: 0 }) });
		expect(readout(j).label).toBe('Failed');
	});
	it('abandoned without rip_progress fails the ID segment', () => {
		const j = job({ status: 'abandoned' });
		expect(states(j)).toEqual(['failed', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'error', label: 'Abandoned', detail: null, figure: null });
	});
	it('abandoned with started tracks in rip_progress fails the RIP segment', () => {
		const j = job({ status: 'abandoned', rip_progress: rp() });
		expect(states(j)).toEqual(['done', 'done', 'failed', 'pending', 'pending']);
		expect(readout(j).label).toBe('Abandoned');
	});
	it('an unknown status shows every segment pending', () => {
		const j = job({ status: 'mystery' });
		expect(states(j)).toEqual(['pending', 'pending', 'pending', 'pending', 'pending']);
		expect(readout(j)).toEqual({ tone: 'default', label: 'Waiting', detail: null, figure: null });
	});
});

describe('jobProgress: unidentified overlay', () => {
	const flagged = { flags: { unidentified: true } };
	it('marks ID attention while identified and while ripping', () => {
		const queued = job({ status: 'identified', metadata_json: flagged });
		expect(states(queued)).toEqual(['attention', 'done', 'active', 'pending', 'pending']);
		expect(readout(queued).detail).toBe('waiting for the drive, no identity');
		const ripping = job({ status: 'ripping', rip_progress: rp(), metadata_json: flagged });
		expect(states(ripping)).toEqual(['attention', 'done', 'active', 'pending', 'pending']);
		expect(readout(ripping).detail).toBe('title 2 of 4, no identity');
	});
	it('joins "no identity" onto the starting detail', () => {
		const j = job({ status: 'ripping', rip_progress: null, metadata_json: flagged });
		expect(readout(j).detail).toBe('starting MakeMKV, no identity');
	});
	it('leaves other statuses alone', () => {
		expect(states(job({ status: 'ripped', metadata_json: flagged }))).toEqual([
			'done',
			'done',
			'done',
			'attention',
			'pending'
		]);
	});
});

describe('jobProgress: review countdown', () => {
	it('fills from wait_start_time over the configured length', () => {
		const v = jobProgress(waiting(), EMPTY_LIVE, CTX);
		expect(v.segments[1].pct).toBe(25);
		expect(v.readout.detail).toBe('starts in 1m 30s');
	});
	it('a shorter length mid-countdown makes it overdue', () => {
		const v = jobProgress(waiting(), EMPTY_LIVE, { ...CTX, reviewWaitSeconds: 20 });
		expect(v.segments[1].pct).toBe(100);
		expect(v.readout).toEqual({ tone: 'default', label: 'Starting', detail: 'waiting for the ripper', figure: null });
	});
	it('a longer length moves the deadline out', () => {
		const v = jobProgress(waiting(), EMPTY_LIVE, { ...CTX, reviewWaitSeconds: 300 });
		expect(v.segments[1].pct).toBe(10);
		expect(v.readout.detail).toBe('starts in 4m 30s');
	});
	it('a length of 0 counts as full', () => {
		const v = jobProgress(waiting(), EMPTY_LIVE, { ...CTX, reviewWaitSeconds: 0 });
		expect(v.segments[1].pct).toBe(100);
		expect(v.readout.label).toBe('Starting');
	});
	it('a clock behind wait_start_time reads as no time elapsed', () => {
		const v = jobProgress(waiting(), EMPTY_LIVE, { ...CTX, now: T0 - 5_000 });
		expect(v.segments[1].pct).toBe(0);
	});
	it('an unreadable wait_start_time reads as no time elapsed', () => {
		const v = jobProgress(waiting({ wait_start_time: 'garbage' }), EMPTY_LIVE, CTX);
		expect(v.segments[1].pct).toBe(0);
		expect(v.readout.detail).toBe('starts in 2m 0s');
	});
});

describe('jobProgress: review case precedence', () => {
	const suggestion = { identity_suggestion: { provider: 'tmdb', title: 'Heat' } };
	const prev = { previously_ripped: { job_id: 'j0' } };
	it('paused wins over a running countdown', () => {
		expect(readout(waiting({ manual_pause: true })).label).toBe('Paused');
		expect(readout(waiting(), EMPTY_LIVE, { ...CTX, rippingPaused: true }).label).toBe('Paused');
		expect(readout(waiting({ wait_start_time: null })).label).toBe('Paused');
	});
	it('episodes_unsure wins over paused', () => {
		expect(readout(waiting({ episodes_unsure: true, manual_pause: true })).label).toBe('Held');
	});
	it('previously ripped wins over episodes_unsure', () => {
		expect(readout(waiting({ episodes_unsure: true, metadata_json: prev })).label).toBe('Ripped before');
	});
	it('a suggestion wins over all', () => {
		const j = waiting({ episodes_unsure: true, manual_pause: true, metadata_json: { ...prev, ...suggestion } });
		expect(readout(j).label).toBe('Confirm the match');
	});
});

describe('isCountingDown', () => {
	it('is true only for the countdown case', () => {
		expect(isCountingDown(waiting(), CTX)).toBe(true);
		expect(isCountingDown(waiting({ manual_pause: true }), CTX)).toBe(false);
		expect(isCountingDown(waiting({ episodes_unsure: true }), CTX)).toBe(false);
		expect(isCountingDown(waiting({ wait_start_time: null }), CTX)).toBe(false);
		expect(isCountingDown(waiting(), { ...CTX, rippingPaused: true })).toBe(false);
		expect(isCountingDown(job({ status: 'ripping' }), CTX)).toBe(false);
	});
});

describe('jobProgress: malformed numbers', () => {
	it('no NaN in the figure', () => {
		const j = job({ status: 'ripping', rip_progress: rp() });
		const v = jobProgress(j, ripLive({ pct: NaN, etaSeconds: 60 }), CTX);
		expect(v.readout.figure).toBe('1 / 4 titles');
		expect(v.segments[2].pct).toBeNull();
		const t = jobProgress(job({ status: 'transcoding' }), encLive({ pct: NaN }), CTX);
		expect(t.readout.figure).toBeNull();
		expect(t.segments[3].pct).toBeNull();
	});
	it('drops a non-finite ETA but keeps the percent', () => {
		const j = job({ status: 'ripping', rip_progress: rp() });
		expect(readout(j, ripLive({ pct: 50, etaSeconds: Infinity })).figure).toBe('50%');
	});
});

describe('ripStageWords', () => {
	it('words the scratch-to-media copy stage plainly', () => {
		expect(ripStageWords('scratch-to-media')).toBe('Copying to shared storage');
	});
	it('words the work-to-completed move stage plainly', () => {
		expect(ripStageWords('work-to-completed')).toBe('Moving to completed');
	});
	it('shows any other stage as the ripper named it', () => {
		expect(ripStageWords('ripping')).toBe('ripping');
	});
	it('is null for no stage', () => {
		expect(ripStageWords(null)).toBeNull();
	});
});

describe('progressSample', () => {
	const transcoding = (percent: number | null) =>
		job({ status: 'transcoding', transcode_progress: percent == null ? null : tp({ percent }) });

	it('prefers the rip sample', () => {
		const live = { rip: sample({ pct: 10 }), transcode: encLive({ pct: 70 }).transcode };
		expect(progressSample(transcoding(30), live)).toBe(live.rip);
	});

	it('uses the live transcode sample when it has a percent', () => {
		const live = encLive({ pct: 70 });
		expect(progressSample(transcoding(30), live)).toBe(live.transcode);
	});

	it('falls back to the snapshot percent with no live transcode sample', () => {
		expect(progressSample(transcoding(30), EMPTY_LIVE)).toEqual({ ...sample(), pct: 30 });
	});

	it('keeps the live fields and takes the snapshot percent when the live percent is missing', () => {
		const out = progressSample(transcoding(30), encLive({ pct: null, etaSeconds: 90 }));
		expect(out).toMatchObject({ pct: 30, etaSeconds: 90 });
	});

	it('a non-finite live percent also falls back', () => {
		expect(progressSample(transcoding(30), encLive({ pct: NaN }))?.pct).toBe(30);
	});

	it('has nothing to fall back to without a snapshot percent', () => {
		expect(progressSample(transcoding(null), EMPTY_LIVE)).toBeNull();
	});

	it('does not fall back for a job that is not transcoding', () => {
		expect(progressSample(job({ status: 'ripped', transcode_progress: null }), EMPTY_LIVE)).toBeNull();
		expect(progressSample(job({ status: 'complete', transcode_progress: tp({ percent: 30 }) }), EMPTY_LIVE)).toBeNull();
	});
});
