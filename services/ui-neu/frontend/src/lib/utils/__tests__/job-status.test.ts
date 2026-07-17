import { describe, it, expect } from 'vitest';
import { effectiveJobStatus, isPartialComplete, reviewPhaseBadge, hasTitleMatch } from '$lib/utils/job-status';

type TP = { state: string; tasks_total: number; tasks_done: number; percent: number } | null;
const job = (status: string, transcode_progress: TP = null) =>
	({ status, transcode_progress }) as any;

describe('effectiveJobStatus', () => {
	it('ripped + no session stays ripped (awaiting action)', () => {
		expect(effectiveJobStatus(job('ripped', null))).toBe('ripped');
	});
	it('ripped + transcoding -> transcoding', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'transcoding', tasks_total: 2, tasks_done: 1, percent: 50 }))).toBe('transcoding');
	});
	it('ripped + done -> complete', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe('complete');
	});
	it('ripped + done_partial -> complete', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))).toBe('complete');
	});
	it('ripped + failed -> failed', () => {
		expect(effectiveJobStatus(job('ripped', { state: 'failed', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe('failed');
	});
	it('ripped_partial + done -> complete', () => {
		expect(effectiveJobStatus(job('ripped_partial', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }))).toBe('complete');
	});
	it('non-post-rip status is unchanged even with a summary', () => {
		expect(effectiveJobStatus(job('ripping', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }))).toBe('ripping');
	});
});

describe('isPartialComplete', () => {
	it('true only for done_partial', () => {
		expect(isPartialComplete(job('ripped', { state: 'done_partial', tasks_total: 2, tasks_done: 1, percent: 50 }))).toBe(true);
		expect(isPartialComplete(job('ripped', { state: 'done', tasks_total: 2, tasks_done: 2, percent: 100 }))).toBe(false);
		expect(isPartialComplete(job('ripped', null))).toBe(false);
	});
});

const badgeJob = (status: string, title: string | null = 'X', transcode_progress: TP = null) =>
	({ status, title, transcode_progress }) as any;

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

describe('reviewPhaseBadge', () => {
	it('awaiting_review -> REVIEW amber', () => {
		const b = reviewPhaseBadge(badgeJob('awaiting_review'));
		expect(b.label).toBe('REVIEW');
		expect(b.accent).toContain('#f59e0b');
	});
	it('awaiting_user_id -> IDENTIFY cyan', () => {
		expect(reviewPhaseBadge(badgeJob('awaiting_user_id')).label).toBe('IDENTIFY');
		expect(reviewPhaseBadge(badgeJob('awaiting_user_id')).accent).toContain('#06b6d4');
	});
	it('ripped_awaiting_identify -> IDENTIFY', () => {
		expect(reviewPhaseBadge(badgeJob('ripped_awaiting_identify')).label).toBe('IDENTIFY');
	});
	it('identified -> READY primary', () => {
		const b = reviewPhaseBadge(badgeJob('identified'));
		expect(b.label).toBe('READY');
		expect(b.accent).toContain('--color-primary');
	});
	it('ripped + no title -> RIPPED · NEEDS SESSION (session wins)', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', null)).label).toBe('RIPPED · NEEDS SESSION');
	});
	it('ripped + has title -> RIPPED · NEEDS SESSION', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', 'MysterySuspense')).label).toBe('RIPPED · NEEDS SESSION');
	});
	it('ripped violet accent', () => {
		expect(reviewPhaseBadge(badgeJob('ripped', null)).accent).toContain('#8b5cf6');
	});
});
