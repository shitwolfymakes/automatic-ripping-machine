import { describe, it, expect } from 'vitest';
import type { JobStatus } from '$lib/types/api.gen';
import {
	isLive,
	isInProgress,
	isAwaitingIdentity,
	lifecycleStageFor,
	LIFECYCLE_FAILURE_STATUSES
} from '../job-status-groups';

const ALL: JobStatus[] = [
	'created',
	'awaiting_user_id',
	'identified',
	'awaiting_review',
	'ripping',
	'ripped',
	'ripped_partial',
	'ripped_awaiting_identify',
	'abandoned',
	'failed'
];

describe('isInProgress', () => {
	const IN_PROGRESS = ['created', 'awaiting_user_id', 'identified', 'awaiting_review', 'ripping'];
	it.each(ALL)('raw status %s with no transcode', (s) => {
		expect(isInProgress({ status: s, transcode_progress: null })).toBe(IN_PROGRESS.includes(s));
	});
	it('a ripped job that is transcoding is in progress', () => {
		expect(
			isInProgress({
				status: 'ripped',
				transcode_progress: { state: 'transcoding', tasks_total: 1, tasks_done: 0, tasks_failed: 0, percent: 10 }
			})
		).toBe(true);
	});
	it('a ripped job whose transcode is done is not in progress', () => {
		expect(
			isInProgress({
				status: 'ripped',
				transcode_progress: { state: 'done', tasks_total: 1, tasks_done: 1, tasks_failed: 0, percent: 100 }
			})
		).toBe(false);
	});
});

describe('isLive', () => {
	it.each(ALL)('raw status %s with no transcode', (s) => {
		expect(isLive({ status: s, transcode_progress: null })).toBe(s !== 'abandoned' && s !== 'failed');
	});
	it('stays live while a ripped job transcodes', () => {
		expect(
			isLive({
				status: 'ripped',
				transcode_progress: { state: 'transcoding', tasks_total: 1, tasks_done: 0, tasks_failed: 0, percent: 10 }
			})
		).toBe(true);
	});
	it.each(['done', 'done_partial', 'failed'] as const)('stops once the transcode is %s', (state) => {
		expect(
			isLive({
				status: 'ripped',
				transcode_progress: { state, tasks_total: 1, tasks_done: 1, tasks_failed: 0, percent: 100 }
			})
		).toBe(false);
	});
	it('treats an unknown future status as live', () => {
		expect(isLive({ status: 'some_new_status' as JobStatus, transcode_progress: null })).toBe(true);
	});
});

describe('isAwaitingIdentity', () => {
	it.each(ALL)('%s', (s) => {
		expect(isAwaitingIdentity(s)).toBe(s === 'awaiting_user_id' || s === 'ripped_awaiting_identify');
	});
});

describe('lifecycleStageFor', () => {
	it.each([
		['created', 'identifying'],
		['awaiting_user_id', 'identifying'],
		['identified', 'identifying'],
		['awaiting_review', 'identifying'],
		['ripping', 'ripping'],
		['ripped', 'ripping'],
		['ripped_partial', 'ripping'],
		['ripped_awaiting_identify', 'ripping'],
		['transcoding', 'transcoding'],
		['complete', 'complete']
	])('%s -> %s', (s, stage) => {
		expect(lifecycleStageFor(s)).toBe(stage);
	});
	it('returns null for failure statuses and unknowns', () => {
		for (const s of [...LIFECYCLE_FAILURE_STATUSES, 'video_ripping']) expect(lifecycleStageFor(s)).toBeNull();
	});
});
