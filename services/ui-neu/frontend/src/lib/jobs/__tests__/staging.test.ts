import { describe, expect, it } from 'vitest';
import {
	followsStageFeed,
	isStageActive,
	showsStageLine,
	stageProgressSample,
	stageSnapshot,
	stageWords,
	waitingForFiles
} from '../staging';
import { EMPTY_SAMPLE } from '$lib/live/feeds';
import type { TrackStageView } from '$lib/types/api.gen';

const stage = (status: TrackStageView['status'], over: Partial<TrackStageView> = {}): TrackStageView => ({
	status,
	bytes_durable: 0,
	source_size: null,
	linked: null,
	attempts: 0,
	last_error: null,
	staged_at: null,
	...over
});

describe('stageWords', () => {
	it.each([
		['pending', 'Waiting to stage'],
		['copying', 'Staging'],
		['stalled', 'Staging stalled'],
		['staged', 'Staged'],
		['failed', 'Staging failed']
	] as const)('names %s', (status, words) => {
		expect(stageWords(stage(status))).toBe(words);
	});
});

describe('isStageActive', () => {
	it.each([
		['pending', true],
		['copying', true],
		['stalled', true],
		['staged', false],
		['failed', false]
	] as const)('%s is %s', (status, active) => {
		expect(isStageActive(stage(status))).toBe(active);
	});
});

describe('showsStageLine', () => {
	it('is false without a stage or once it is staged', () => {
		expect(showsStageLine(null)).toBe(false);
		expect(showsStageLine(undefined)).toBe(false);
		expect(showsStageLine(stage('staged'))).toBe(false);
	});

	it('is true for every other status', () => {
		expect(showsStageLine(stage('pending'))).toBe(true);
		expect(showsStageLine(stage('failed'))).toBe(true);
	});
});

describe('followsStageFeed', () => {
	it('follows only a copy in flight', () => {
		expect(followsStageFeed(stage('copying'))).toBe(true);
		expect(followsStageFeed(stage('pending'))).toBe(false);
		expect(followsStageFeed(null)).toBe(false);
	});
});

describe('waitingForFiles', () => {
	it('is true for a queued encode whose copy is not staged', () => {
		expect(waitingForFiles({ transcode_status: 'queued', stage: stage('copying') })).toBe(true);
		expect(waitingForFiles({ transcode_status: 'queued', stage: stage('failed') })).toBe(true);
	});

	it('is false once staged, with no stage, or when the task is not queued', () => {
		expect(waitingForFiles({ transcode_status: 'queued', stage: stage('staged') })).toBe(false);
		expect(waitingForFiles({ transcode_status: 'queued', stage: null })).toBe(false);
		expect(waitingForFiles({ transcode_status: 'in_progress', stage: stage('copying') })).toBe(false);
		expect(waitingForFiles({ transcode_status: null, stage: stage('copying') })).toBe(false);
	});
});

describe('stageSnapshot and stageProgressSample', () => {
	it('draws the checkpoint bytes as a percent of the source', () => {
		expect(stageSnapshot(stage('copying', { bytes_durable: 25, source_size: 100 }))).toEqual({
			...EMPTY_SAMPLE,
			pct: 25,
			bytesDone: 25,
			bytesTotal: 100
		});
	});

	it('has no percent before the source size is known', () => {
		expect(stageSnapshot(stage('pending'))).toMatchObject({ pct: null, bytesDone: 0, bytesTotal: null });
	});

	it('prefers the live report over the checkpoint', () => {
		const live = { ...EMPTY_SAMPLE, pct: 60 };
		expect(stageProgressSample(stage('copying', { source_size: 100 }), live)).toBe(live);
		expect(stageProgressSample(stage('copying', { source_size: 100 }), null).pct).toBe(0);
	});
});
