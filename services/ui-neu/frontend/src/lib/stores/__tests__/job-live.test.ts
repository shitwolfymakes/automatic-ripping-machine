import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { writable } from 'svelte/store';
import type { TranscodeTaskView } from '$lib/types/api.gen';

type Handler = (env: { payload: Record<string, unknown> }) => void;
const handlers = new Map<string, Handler>();
const subscribe = vi.fn((topic: string, h: Handler) => {
	handlers.set(topic, h);
	return () => handlers.delete(topic);
});
vi.mock('$lib/api/ws', () => ({ wsClient: { subscribe: (t: string, h: never) => subscribe(t, h) } }));

const dash = writable<{ active_transcodes?: Record<string, unknown>[] }>({ active_transcodes: [] });
const dashSubscribe = vi.fn((fn: never) => dash.subscribe(fn));
vi.mock('$lib/stores/dashboard', () => ({ dashboard: { subscribe: (fn: never) => dashSubscribe(fn) } }));

const { JobLiveStore, EMPTY_LIVE, jobLive } = await import('../job-live.svelte');

function row(over: Record<string, unknown> = {}): TranscodeTaskView {
	return {
		id: 'k1',
		job_id: 'j1',
		status: 'in_progress',
		progress_pct: 10,
		eta_seconds: null,
		fps: null,
		avg_fps: null,
		current_pass: null,
		started_at: null,
		...over
	} as unknown as TranscodeTaskView;
}

const tick = (topic: string, payload: Record<string, unknown>) => handlers.get(topic)?.({ payload });

beforeEach(() => {
	handlers.clear();
	subscribe.mockClear();
	dashSubscribe.mockClear();
	dash.set({ active_transcodes: [] });
});

afterEach(() => {
	vi.useRealTimers();
});

describe('JobLiveStore', () => {
	it('exports an empty record and a shared instance', () => {
		expect(EMPTY_LIVE).toEqual({ rip: null, transcode: null });
		expect(jobLive).toBeInstanceOf(JobLiveStore);
	});

	it('two watchers of a ripping job share one subscription', () => {
		const store = new JobLiveStore();
		const offA = store.watch({ id: 'j1', status: 'ripping' });
		const offB = store.watch({ id: 'j1', status: 'ripping' });
		expect(subscribe).toHaveBeenCalledTimes(1);
		tick('ripper.progress.j1', { track_id: 't1', progress_pct: 42 });
		expect(store.get('j1').rip?.pct).toBe(42);
		offA();
		offB();
	});

	it('keeps the feed for the remaining watcher', () => {
		const store = new JobLiveStore();
		const offA = store.watch({ id: 'j1', status: 'ripping' });
		const offB = store.watch({ id: 'j1', status: 'ripping' });
		offA();
		expect(handlers.has('ripper.progress.j1')).toBe(true);
		tick('ripper.progress.j1', { progress_pct: 55 });
		expect(store.get('j1').rip?.pct).toBe(55);
		offB();
	});

	it('releases the rip topic and clears its sample when the last watcher leaves', () => {
		const store = new JobLiveStore();
		const offA = store.watch({ id: 'j1', status: 'ripping' });
		const offB = store.watch({ id: 'j1', status: 'ripping' });
		tick('ripper.progress.j1', { progress_pct: 42 });
		offA();
		offB();
		expect(handlers.has('ripper.progress.j1')).toBe(false);
		expect(store.get('j1').rip).toBeNull();
	});

	it('starts a fresh feed when a job is watched again after release', () => {
		const store = new JobLiveStore();
		store.watch({ id: 'j1', status: 'ripping' })();
		const off = store.watch({ id: 'j1', status: 'ripping' });
		tick('ripper.progress.j1', { progress_pct: 7 });
		expect(store.get('j1').rip?.pct).toBe(7);
		off();
	});

	it('a second call to the same unwatch changes nothing', () => {
		const store = new JobLiveStore();
		const offA = store.watch({ id: 'j1', status: 'ripping' });
		const offB = store.watch({ id: 'j1', status: 'ripping' });
		offA();
		offA();
		expect(handlers.has('ripper.progress.j1')).toBe(true);
		tick('ripper.progress.j1', { progress_pct: 21 });
		expect(store.get('j1').rip?.pct).toBe(21);
		offB();
		expect(handlers.size).toBe(0);
	});

	it('a second call to the same unfollow changes nothing', () => {
		const store = new JobLiveStore();
		const offA = store.followTask('k1');
		const offB = store.followTask('k1');
		offA();
		offA();
		tick('transcode.progress.k1', { progress_pct: 9 });
		expect(store.task('k1')?.pct).toBe(9);
		offB();
		expect(handlers.size).toBe(0);
	});

	it('a status change from ripping to ripped releases the rip topic with no leak', () => {
		// The order a surface's $effect runs on a status change: the old watch's
		// cleanup, then the new watch.
		const store = new JobLiveStore();
		const offRipping = store.watch({ id: 'j1', status: 'ripping' });
		tick('ripper.progress.j1', { progress_pct: 42 });
		expect(store.get('j1').rip?.pct).toBe(42);
		offRipping();
		const offRipped = store.watch({ id: 'j1', status: 'ripped' });
		expect(handlers.has('ripper.progress.j1')).toBe(false);
		expect(subscribe.mock.calls.filter(([topic]) => topic === 'ripper.progress.j1')).toHaveLength(1);
		expect(store.get('j1').rip).toBeNull();
		offRipped();
		expect(handlers.size).toBe(0);
	});

	it('holds no rip topic for a job that is not ripping', () => {
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'identified' });
		expect(handlers.has('ripper.progress.j1')).toBe(false);
		expect(store.get('j1')).toEqual(EMPTY_LIVE);
		off();
	});

	it("follows a watched job's in-progress task and merges its sample over the row", () => {
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		dash.set({
			active_transcodes: [
				row({ eta_seconds: 900, fps: 5, avg_fps: 4, current_pass: '1/2' }),
				row({ id: 'k2', job_id: 'other' }),
				row({ id: 'k3', status: 'pending' }),
				row({ id: 'k4', job_id: null })
			]
		});
		expect([...handlers.keys()]).toEqual(['transcode.progress.k1']);
		expect(store.get('j1').transcode).toMatchObject({
			taskId: 'k1',
			pct: 10,
			etaSeconds: 900,
			fps: 5,
			avgFps: 4,
			pass: '1/2',
			bytesDone: null,
			phase: null,
			trackId: null
		});
		tick('transcode.progress.k1', { progress_pct: 60, fps: 48, current_pass: '2/2' });
		expect(store.get('j1').transcode).toMatchObject({ pct: 60, etaSeconds: 900, fps: 48, avgFps: 4, pass: '2/2' });
		off();
	});

	it('ETA falls back to the row, then to an estimate from started_at', () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-01-01T01:00:00Z'));
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		dash.set({ active_transcodes: [row({ eta_seconds: 900, progress_pct: 50, started_at: '2026-01-01T00:00:00Z' })] });
		tick('transcode.progress.k1', { progress_pct: 60, eta_seconds: 120 });
		expect(store.get('j1').transcode?.etaSeconds).toBe(120);
		tick('transcode.progress.k1', { progress_pct: 60 });
		expect(store.get('j1').transcode?.etaSeconds).toBe(900);
		dash.set({ active_transcodes: [row({ eta_seconds: null, progress_pct: 50, started_at: '2026-01-01T00:00:00Z' })] });
		expect(store.get('j1').transcode?.etaSeconds).toBe(3600);
		dash.set({ active_transcodes: [row({ eta_seconds: null, progress_pct: 50, started_at: null })] });
		expect(store.get('j1').transcode?.etaSeconds).toBeNull();
		off();
	});

	it('drops a task topic when the task leaves active_transcodes', () => {
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		dash.set({ active_transcodes: [row()] });
		tick('transcode.progress.k1', { progress_pct: 60 });
		dash.set({ active_transcodes: [] });
		expect(handlers.size).toBe(0);
		expect(store.task('k1')).toBeNull();
		off();
	});

	it('drops task topics when the job is unwatched, keeping a followed one', () => {
		const store = new JobLiveStore();
		const offJob = store.watch({ id: 'j1', status: 'ripped' });
		dash.set({ active_transcodes: [row()] });
		const offTask = store.followTask('k1');
		offJob();
		expect(handlers.has('transcode.progress.k1')).toBe(true);
		offTask();
		expect(handlers.has('transcode.progress.k1')).toBe(false);
	});

	it('followTask holds the topic without a watched job', () => {
		const store = new JobLiveStore();
		const off = store.followTask('k9');
		expect(handlers.has('transcode.progress.k9')).toBe(true);
		expect(store.task('k9')).toBeNull();
		tick('transcode.progress.k9', { progress_pct: 33, fps: 20 });
		expect(store.task('k9')).toMatchObject({ taskId: 'k9', pct: 33, fps: 20, etaSeconds: null });
		expect(store.task('k9', null)).toMatchObject({ pct: 33 });
		expect(store.task('k9', row({ id: 'k9', progress_pct: 5, fps: 99, avg_fps: 8 }))).toMatchObject({
			pct: 33,
			fps: 20,
			avgFps: 8
		});
		off();
		expect(handlers.size).toBe(0);
		expect(store.task('k9')).toBeNull();
	});

	it('followStage holds the staging topic, reads its sample and releases it once', () => {
		const store = new JobLiveStore();
		const offA = store.followStage('t1');
		const offB = store.followStage('t1');
		expect(subscribe).toHaveBeenCalledTimes(1);
		expect(store.stage('t1')).toBeNull();
		tick('staging.progress.t1', { track_id: 't1', bytes_done: 5, bytes_total: 10, rate_bps: 2 });
		expect(store.stage('t1')).toMatchObject({ pct: 50, bytesDone: 5, rateBps: 2 });
		offA();
		offA();
		expect(handlers.has('staging.progress.t1')).toBe(true);
		offB();
		expect(handlers.has('staging.progress.t1')).toBe(false);
		expect(store.stage('t1')).toBeNull();
	});

	it('task() reads a row alone when there is no live sample', () => {
		const store = new JobLiveStore();
		expect(store.task('k1', row({ current_pass: '1/2' }))).toMatchObject({ taskId: 'k1', pct: 10, pass: '1/2' });
	});

	it('falls back to the snapshot percent with no task row', () => {
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		expect(store.get('j1').transcode).toBeNull();
		off();
	});

	it('copes with a dashboard value that has no active_transcodes', () => {
		const store = new JobLiveStore();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		dash.set({});
		expect(store.get('j1').transcode).toBeNull();
		off();
	});

	it('does not subscribe to the dashboard until first use', () => {
		const store = new JobLiveStore();
		expect(dashSubscribe).not.toHaveBeenCalled();
		store.get('j1');
		expect(dashSubscribe).not.toHaveBeenCalled();
		const off = store.watch({ id: 'j1', status: 'ripped' });
		const off2 = store.followTask('k1');
		expect(dashSubscribe).toHaveBeenCalledTimes(1);
		off();
		off2();
	});
});
