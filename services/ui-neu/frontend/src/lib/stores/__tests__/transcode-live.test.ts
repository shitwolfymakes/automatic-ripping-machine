import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { WSEnvelope } from '$lib/api/ws';
import { liveSample } from '$lib/transcode/progress';
import { TranscodeLive } from '../transcode-live.svelte';

const wsHandlers = new Map<string, (env: WSEnvelope) => void>();
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: vi.fn((topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandlers.set(topic, handler);
			return () => wsHandlers.delete(topic);
		})
	}
}));

import { wsClient } from '$lib/api/ws';

function progressEvent(taskId: string, payload: Record<string, unknown>): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: 'transcode.progress',
		emitted_at: '2025-06-15T12:00:00Z',
		topic: `transcode.progress.${taskId}`,
		job_id: null,
		track_id: null,
		payload: { task_id: taskId, ...payload }
	};
}

function publish(taskId: string, payload: Record<string, unknown>): void {
	wsHandlers.get(`transcode.progress.${taskId}`)!(progressEvent(taskId, payload));
}

describe('TranscodeLive', () => {
	beforeEach(() => {
		wsHandlers.clear();
		vi.mocked(wsClient.subscribe).mockClear();
	});

	it('follows the task topic and returns the unsubscribe', () => {
		const live = new TranscodeLive();
		const unsubscribe = live.follow('t-1');
		expect(wsClient.subscribe).toHaveBeenCalledWith('transcode.progress.t-1', expect.any(Function));
		expect(wsHandlers.has('transcode.progress.t-1')).toBe(true);
		unsubscribe();
		expect(wsHandlers.has('transcode.progress.t-1')).toBe(false);
	});

	it('turns a published payload into the sample', () => {
		const live = new TranscodeLive();
		live.follow('t-1');
		const payload = { eta_seconds: 90, fps: 24, avg_fps: 22 };
		publish('t-1', payload);
		expect(live.sampleFor('t-1')).toEqual(liveSample('t-1', payload));
	});

	it('replaces the earlier sample with a later payload', () => {
		const live = new TranscodeLive();
		live.follow('t-1');
		publish('t-1', { eta_seconds: 90, fps: 24, avg_fps: 22 });
		publish('t-1', { eta_seconds: 30, fps: 30, avg_fps: 25 });
		expect(live.sampleFor('t-1')).toEqual(liveSample('t-1', { eta_seconds: 30, fps: 30, avg_fps: 25 }));
	});

	it('returns null before any sample', () => {
		expect(new TranscodeLive().sampleFor('t-1')).toBeNull();
	});

	it('returns null for another task id', () => {
		const live = new TranscodeLive();
		live.follow('t-1');
		publish('t-1', { eta_seconds: 90 });
		expect(live.sampleFor('t-2')).toBeNull();
	});

	it('returns null for an undefined task id', () => {
		const live = new TranscodeLive();
		live.follow('t-1');
		publish('t-1', { eta_seconds: 90 });
		expect(live.sampleFor(undefined)).toBeNull();
	});

	it('keeps a separate sample per instance', () => {
		const a = new TranscodeLive();
		const b = new TranscodeLive();
		a.follow('t-1');
		publish('t-1', { eta_seconds: 90 });
		expect(a.sampleFor('t-1')).not.toBeNull();
		expect(b.sampleFor('t-1')).toBeNull();
	});
});
