import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { etaTime, formatRemaining } from '../../utils/format';
import { formatFps } from '../fps';
import { etaLabel, fpsLabel, liveSample, type TranscodeLiveSample } from '../progress';

function sample(values: Partial<TranscodeLiveSample>): TranscodeLiveSample {
	return { taskId: 't1', eta: null, fps: null, avgFps: null, ...values };
}

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

describe('etaLabel', () => {
	const NOW = new Date('2026-01-01T01:00:00Z');
	const STARTED = '2026-01-01T00:00:00Z';

	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(NOW);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("prefers the sample's ETA over the task's eta_seconds", () => {
		const task = { eta_seconds: 600, started_at: STARTED, progress_pct: 50 };
		expect(etaLabel(task, sample({ eta: 90 }))).toBe(formatRemaining(90));
	});

	it('uses a sample ETA of 0', () => {
		const task = { eta_seconds: 600, started_at: null, progress_pct: 0 };
		expect(etaLabel(task, sample({ eta: 0 }))).toBe(formatRemaining(0));
	});

	it.each([
		['a null sample', null],
		['a sample with a null ETA', sample({ eta: null })]
	])("falls back to the task's eta_seconds for %s", (_name, live) => {
		const task = { eta_seconds: 600, started_at: null, progress_pct: 0 };
		expect(etaLabel(task, live)).toBe(formatRemaining(600));
	});

	it('estimates from started_at when neither the sample nor the task has an ETA', () => {
		const task = { eta_seconds: null, started_at: STARTED, progress_pct: 50 };
		expect(etaLabel(task, null)).toBe(etaTime(STARTED, 50));
		expect(etaLabel(task, null)).toBe(formatRemaining(3600));
	});

	it('is null when the estimate has no progress to go on', () => {
		const task = { eta_seconds: null, started_at: STARTED, progress_pct: 0 };
		expect(etaLabel(task, null)).toBeNull();
	});

	it('is null without a started_at', () => {
		const task = { eta_seconds: null, started_at: null, progress_pct: 50 };
		expect(etaLabel(task, null)).toBeNull();
	});
});

describe('fpsLabel', () => {
	const task = { fps: 10, avg_fps: 9 };

	it("uses the sample's fps with its average", () => {
		expect(fpsLabel(task, sample({ fps: 24.5, avgFps: 23 }))).toBe(formatFps(24.5, 23));
	});

	it('uses the sample fps alone when its average is null', () => {
		expect(fpsLabel(task, sample({ fps: 24.5, avgFps: null }))).toBe(formatFps(24.5, null));
	});

	it('uses a sample fps of 0', () => {
		expect(fpsLabel(task, sample({ fps: 0, avgFps: 0 }))).toBe(formatFps(0, 0));
	});

	it.each([
		['a null sample', null],
		['a sample with a null fps', sample({ fps: null, avgFps: 5 })]
	])("falls back to the task's fps and avg_fps for %s", (_name, live) => {
		expect(fpsLabel(task, live)).toBe(formatFps(10, 9));
	});

	it('is null when neither the sample nor the task has an fps', () => {
		expect(fpsLabel({ fps: null, avg_fps: null }, null)).toBeNull();
	});
});
