import { describe, expect, it } from 'vitest';
import { liveSample } from '../transcode-progress';

describe('liveSample', () => {
	it('carries all three values when they are numbers', () => {
		expect(liveSample('t1', { eta_seconds: 120, fps: 24.5, avg_fps: 23 })).toEqual({
			taskId: 't1',
			eta: 120,
			fps: 24.5,
			avgFps: 23
		});
	});

	it('keeps zero as a number', () => {
		expect(liveSample('t1', { eta_seconds: 0, fps: 0, avg_fps: 0 })).toEqual({
			taskId: 't1',
			eta: 0,
			fps: 0,
			avgFps: 0
		});
	});

	it.each([
		['eta_seconds', { fps: 1, avg_fps: 2 }, { eta: null, fps: 1, avgFps: 2 }],
		['fps', { eta_seconds: 3, avg_fps: 2 }, { eta: 3, fps: null, avgFps: 2 }],
		['avg_fps', { eta_seconds: 3, fps: 1 }, { eta: 3, fps: 1, avgFps: null }]
	])('is null for a missing %s', (_name, payload, expected) => {
		expect(liveSample('t1', payload)).toEqual({ taskId: 't1', ...expected });
	});

	it.each([
		['a string', '5'],
		['null', null]
	])('is null for each value that is %s', (_name, value) => {
		expect(liveSample('t1', { eta_seconds: value, fps: value, avg_fps: value })).toEqual({
			taskId: 't1',
			eta: null,
			fps: null,
			avgFps: null
		});
	});

	it('passes NaN through, since NaN is a number', () => {
		const sample = liveSample('t1', { eta_seconds: NaN, fps: NaN, avg_fps: NaN });
		expect(sample.eta).toBeNaN();
		expect(sample.fps).toBeNaN();
		expect(sample.avgFps).toBeNaN();
	});

	it("uses the task id passed in, not the payload's task_id", () => {
		expect(liveSample('mine', { task_id: 'other' }).taskId).toBe('mine');
	});
});
