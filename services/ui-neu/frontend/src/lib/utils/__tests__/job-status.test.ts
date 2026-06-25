import { describe, it, expect } from 'vitest';
import { effectiveJobStatus, isPartialComplete } from '$lib/utils/job-status';

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
