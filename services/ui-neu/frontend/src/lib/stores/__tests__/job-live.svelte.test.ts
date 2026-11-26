import { describe, it, expect, vi, beforeEach } from 'vitest';
import { flushSync } from 'svelte';
import { writable } from 'svelte/store';

type Handler = (env: { payload: Record<string, unknown> }) => void;
const handlers = new Map<string, Handler>();
const subscribe = vi.fn((topic: string, h: Handler) => {
	handlers.set(topic, h);
	return () => handlers.delete(topic);
});
vi.mock('$lib/api/ws', () => ({ wsClient: { subscribe: (t: string, h: never) => subscribe(t, h) } }));

const dash = writable<{ active_transcodes: Record<string, unknown>[] }>({ active_transcodes: [] });
vi.mock('$lib/stores/dashboard', () => ({ dashboard: { subscribe: (fn: never) => dash.subscribe(fn) } }));

const { JobLiveStore } = await import('../job-live.svelte');

beforeEach(() => {
	handlers.clear();
	subscribe.mockClear();
	dash.set({ active_transcodes: [] });
});

describe('JobLiveStore inside effects', () => {
	it('watch does not make the caller effect depend on dashboard updates', () => {
		const store = new JobLiveStore();
		let runs = 0;
		const stop = $effect.root(() => {
			$effect(() => {
				runs++;
				return store.watch({ id: 'j1', status: 'ripping' });
			});
		});
		flushSync();
		handlers.get('ripper.progress.j1')?.({ payload: { progress_pct: 42 } });
		dash.set({ active_transcodes: [{ id: 'k1', job_id: 'j1', status: 'in_progress', progress_pct: 1 }] });
		flushSync();
		expect(runs).toBe(1);
		expect(subscribe.mock.calls.filter(([t]) => t === 'ripper.progress.j1')).toHaveLength(1);
		expect(store.get('j1').rip?.pct).toBe(42);
		stop();
		flushSync();
		expect(handlers.size).toBe(0);
	});

	it('followTask does not make the caller effect depend on dashboard updates', () => {
		const store = new JobLiveStore();
		let runs = 0;
		const stop = $effect.root(() => {
			$effect(() => {
				runs++;
				return store.followTask('k1');
			});
		});
		flushSync();
		handlers.get('transcode.progress.k1')?.({ payload: { progress_pct: 30 } });
		dash.set({ active_transcodes: [{ id: 'k1', job_id: 'j1', status: 'in_progress', progress_pct: 1 }] });
		flushSync();
		expect(runs).toBe(1);
		expect(subscribe).toHaveBeenCalledTimes(1);
		expect(store.task('k1')?.pct).toBe(30);
		stop();
		flushSync();
		expect(handlers.size).toBe(0);
	});
});
