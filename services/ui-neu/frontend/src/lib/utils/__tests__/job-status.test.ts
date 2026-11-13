import { describe, it, expect } from 'vitest';
import { effectiveJobStatus, isPartialComplete, hasTitleMatch, isAwaitingAction, countRipping } from '$lib/jobs/status';

type TP = { state: string; tasks_total: number; tasks_done: number; percent: number } | null;
const job = (status: string, transcode_progress: TP = null) => ({ status, transcode_progress }) as any;

describe('effectiveJobStatus', () => {
	it('ripped + no session stays ripped (awaiting action)', () => {
		expect(effectiveJobStatus(job('ripped', null))).toBe('ripped');
	});
	it('ripped + transcoding -> transcoding', () => {
		expect(
			effectiveJobStatus(job('ripped', { state: 'transcoding', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe('transcoding');
	});
	it('ripped + done -> complete', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe(
			'complete'
		);
	});
	it('ripped + done_partial -> transcode_failed (not complete — some tracks failed)', () => {
		expect(
			effectiveJobStatus(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe('transcode_failed');
	});
	it('ripped + failed -> transcode_failed (all tracks failed; rip itself was fine)', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'failed', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe(
			'transcode_failed'
		);
	});
	it('ripped_partial + done -> complete', () => {
		expect(
			effectiveJobStatus(job('ripped_partial', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }))
		).toBe('complete');
	});
	it('non-post-rip status is unchanged even with a summary', () => {
		expect(
			effectiveJobStatus(job('ripping', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }))
		).toBe('ripping');
	});
});

describe('isPartialComplete', () => {
	it('true only for done_partial', () => {
		expect(
			isPartialComplete(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))
		).toBe(true);
		expect(isPartialComplete(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe(
			false
		);
		expect(isPartialComplete(job('ripped', null))).toBe(false);
	});
});

describe('hasTitleMatch', () => {
	it('true for a non-empty title', () => {
		expect(hasTitleMatch({ title: 'MysterySuspense' } as any)).toBe(true);
	});
	it('false for null / empty / whitespace title', () => {
		expect(hasTitleMatch({ title: null } as any)).toBe(false);
		expect(hasTitleMatch({ title: '' } as any)).toBe(false);
		expect(hasTitleMatch({ title: '   ' } as any)).toBe(false);
	});
});

import { transcodeColumnStatus } from '$lib/jobs/status';

const tp = (state: string, tasks_total: number, tasks_done: number, tasks_failed: number) =>
	({ status: 'ripped', transcode_progress: { state, tasks_total, tasks_done, tasks_failed, percent: 0 } }) as any;

describe('transcodeColumnStatus', () => {
	it('null when no transcode_progress', () => {
		expect(transcodeColumnStatus({ status: 'ripped', transcode_progress: null } as any)).toBeNull();
	});
	it('done -> Complete/complete (green; the all-succeed gate)', () => {
		expect(transcodeColumnStatus(tp('done', 4, 4, 0))).toEqual({ label: 'Complete', badgeStatus: 'complete' });
	});
	it('done_partial -> Transcode failed (red)', () => {
		expect(transcodeColumnStatus(tp('done_partial', 4, 2, 2))).toEqual({
			label: 'Transcode failed',
			badgeStatus: 'transcode_failed'
		});
	});
	it('failed -> Transcode failed (red)', () => {
		expect(transcodeColumnStatus(tp('failed', 4, 0, 4))).toEqual({
			label: 'Transcode failed',
			badgeStatus: 'transcode_failed'
		});
	});
	it('transcoding + tasks_failed>0 -> Failed — retrying (red, never green/blue)', () => {
		expect(transcodeColumnStatus(tp('transcoding', 4, 1, 1))).toEqual({
			label: 'Failed, retrying 1/4',
			badgeStatus: 'transcode_failed'
		});
	});
	it('transcoding + no failures -> Transcoding N/M (blue)', () => {
		expect(transcodeColumnStatus(tp('transcoding', 4, 2, 0))).toEqual({
			label: 'Transcoding 2/4',
			badgeStatus: 'transcoding'
		});
	});
});

describe('missing or unknown values', () => {
	it('effectiveJobStatus of a job without a status is an empty string', () => {
		expect(effectiveJobStatus({ status: undefined, transcode_progress: null } as any)).toBe('');
	});
	it('isAwaitingAction is false without a status, true for a ripped job with no session', () => {
		expect(isAwaitingAction({ status: undefined, transcode_progress: null } as any)).toBe(false);
		expect(isAwaitingAction(job('ripped', null))).toBe(true);
	});
	it('transcodeColumnStatus of an unknown transcode state is null', () => {
		expect(transcodeColumnStatus(tp('mystery', 4, 1, 0))).toBeNull();
	});
	it('isAwaitingAction is true for a ripped_partial job with no session', () => {
		expect(isAwaitingAction(job('ripped_partial', null))).toBe(true);
	});
	it('countRipping counts only jobs in the ripping status', () => {
		expect(countRipping([job('ripping'), job('ripped'), job('ripping'), job('complete')])).toBe(2);
	});
});
