import { describe, expect, it } from 'vitest';
import { createRipFeed, estimateEtaSeconds, transcodeSample } from '../feeds';

describe('rip feed', () => {
	it('no ETA on the first tick', () => {
		const feed = createRipFeed();
		const sample = feed({ track_id: 't1', progress_pct: 10 }, 0);
		expect(sample.pct).toBe(10);
		expect(sample.trackId).toBe('t1');
		expect(sample.etaSeconds).toBeNull();
	});

	it('percent ETA after 5 s and 0.5 points', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 10 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 20 }, 10_000).etaSeconds).toBe(80);
	});

	it('keeps the ETA null when the window is too short or too flat', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 10 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 20 }, 2_000).etaSeconds).toBeNull();
		expect(feed({ track_id: 't1', progress_pct: 10.2 }, 10_000).etaSeconds).toBeNull();
	});

	it('keeps its baseline when the rip moves to the next track, since the percentage is for the whole disc', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 10 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 20 }, 10_000).etaSeconds).toBe(80);
		// 20 points in 20 s from the first sample → 1 point/s → 70 points left → 70 s.
		const next = feed({ track_id: 't2', progress_pct: 30 }, 20_000);
		expect(next.trackId).toBe('t2');
		expect(next.etaSeconds).toBe(70);
	});

	it('resets on a backwards jump of more than 1 point', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 50 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 60 }, 10_000).etaSeconds).toBe(40);
		expect(feed({ track_id: 't1', progress_pct: 20 }, 20_000).etaSeconds).toBeNull();
	});

	it('does not reset on a backwards step of 1 point or less', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 50 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 49.5 }, 10_000).etaSeconds).toBeNull();
		expect(feed({ track_id: 't1', progress_pct: 60 }, 20_000).etaSeconds).toBe(80);
	});

	it('byte ETA wins when rate is reported', () => {
		const feed = createRipFeed();
		const sample = feed({ track_id: 't1', progress_pct: 33, bytes_done: 1000, bytes_total: 3000, rate_bps: 100 }, 0);
		expect(sample.etaSeconds).toBe(20);
		expect(sample.bytesDone).toBe(1000);
		expect(sample.bytesTotal).toBe(3000);
		expect(sample.rateBps).toBe(100);
	});

	it('byte ETA never goes negative', () => {
		const feed = createRipFeed();
		const sample = feed({ track_id: 't1', progress_pct: 100, bytes_done: 4000, bytes_total: 3000, rate_bps: 100 }, 0);
		expect(sample.etaSeconds).toBe(0);
	});

	it.each([
		['a zero rate', { rate_bps: 0, bytes_done: 1, bytes_total: 2 }],
		['no bytes done', { rate_bps: 5, bytes_total: 2 }],
		['no bytes total', { rate_bps: 5, bytes_done: 1 }]
	])('has no byte ETA with %s', (_name, extra) => {
		const feed = createRipFeed();
		expect(feed({ track_id: 't1', progress_pct: 10, ...extra }, 0).etaSeconds).toBeNull();
	});

	it('a published eta_seconds is used as is', () => {
		const feed = createRipFeed();
		const sample = feed(
			{ track_id: 't1', progress_pct: 10, eta_seconds: 42, rate_bps: 100, bytes_done: 0, bytes_total: 9 },
			0
		);
		expect(sample.etaSeconds).toBe(42);
	});

	it('a published eta_seconds beats the percent ETA on later ticks', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 10 }, 0);
		expect(feed({ track_id: 't1', progress_pct: 20, eta_seconds: 7 }, 10_000).etaSeconds).toBe(7);
	});

	it('clamps a published negative eta_seconds to 0', () => {
		const feed = createRipFeed();
		expect(feed({ track_id: 't1', progress_pct: 10, eta_seconds: -5 }, 0).etaSeconds).toBe(0);
	});

	it('carries the phase', () => {
		const feed = createRipFeed();
		expect(feed({ track_id: 't1', progress_pct: 100, phase: 'verifying' }, 0).phase).toBe('verifying');
	});

	it('reads a payload without a percent as null fields and does not move the baseline', () => {
		const feed = createRipFeed();
		feed({ track_id: 't1', progress_pct: 10 }, 0);
		const blank = feed({ track_id: 't1', progress_pct: '50', rate_bps: 10, bytes_done: 0, bytes_total: 100 }, 5_000);
		expect(blank.pct).toBeNull();
		expect(blank.etaSeconds).toBe(10);
		expect(feed({ track_id: 't1', progress_pct: 20 }, 10_000).etaSeconds).toBe(80);
	});

	it('non-numeric fields read as null', () => {
		const feed = createRipFeed();
		const sample = feed({ progress_pct: NaN, track_id: 5, phase: 3, eta_seconds: '9', rate_bps: null }, 0);
		expect(sample).toEqual({
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
		});
	});
});

describe('transcode sample', () => {
	it('reads pct, eta, fps, avg fps and pass', () => {
		expect(
			transcodeSample({ progress_pct: 40, eta_seconds: 120, fps: 24.5, avg_fps: 23, current_pass: '1/2' })
		).toEqual({
			pct: 40,
			etaSeconds: 120,
			fps: 24.5,
			avgFps: 23,
			pass: '1/2',
			bytesDone: null,
			bytesTotal: null,
			rateBps: null,
			phase: null,
			trackId: null
		});
	});

	it('keeps zero as a number', () => {
		const sample = transcodeSample({ progress_pct: 0, eta_seconds: 0, fps: 0, avg_fps: 0 });
		expect([sample.pct, sample.etaSeconds, sample.fps, sample.avgFps]).toEqual([0, 0, 0, 0]);
	});

	it('non-numeric fields read as null', () => {
		const sample = transcodeSample({
			progress_pct: '50',
			eta_seconds: null,
			fps: NaN,
			avg_fps: Infinity,
			current_pass: 2
		});
		expect([sample.pct, sample.etaSeconds, sample.fps, sample.avgFps, sample.pass]).toEqual([
			null,
			null,
			null,
			null,
			null
		]);
	});

	it('reads an empty payload as all null', () => {
		expect(transcodeSample({}).pct).toBeNull();
	});
});

describe('estimateEtaSeconds', () => {
	const START = '2026-01-01T00:00:00Z';
	const at = (seconds: number) => new Date(START).getTime() + seconds * 1000;

	it('is null under 30 s elapsed', () => {
		expect(estimateEtaSeconds(START, 50, at(29))).toBeNull();
	});

	it('extrapolates from elapsed time and percent', () => {
		expect(estimateEtaSeconds(START, 50, at(100))).toBe(100);
	});

	it.each([
		['no start', null, 50],
		['an empty start', '', 50],
		['no percent', START, null],
		['an undefined percent', START, undefined],
		['zero percent', START, 0],
		['100 percent', START, 100],
		['a NaN percent', START, NaN],
		['an unparseable start', 'not a date', 50]
	])('is null with %s', (_name, startedAt, pct) => {
		expect(estimateEtaSeconds(startedAt, pct, at(100))).toBeNull();
	});
});
