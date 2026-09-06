import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { WSEnvelope } from '$lib/api/ws';
import type { LogEntry } from '$lib/api/logs';

const fetchJobLogMock = vi.fn();
vi.mock('$lib/api/logs', async (orig) => {
	const actual = (await orig()) as Record<string, unknown>;
	return { ...actual, fetchJobLog: (...a: unknown[]) => fetchJobLogMock(...a) };
});

const subscribeMock = vi.fn();
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => subscribeMock(topic, handler)
	}
}));

import { createJobLog } from '$lib/stores/jobLog.svelte';

function logLineEnv(jobId: string, raw: Record<string, unknown>): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: 'log.line',
		emitted_at: 'now',
		topic: `logs.${jobId}`,
		job_id: jobId,
		track_id: null,
		payload: raw
	};
}

const ENTRY_A: LogEntry = {
	timestamp: '2026-09-05T00:00:01Z',
	level: 'info',
	logger: 'arm',
	event: 'started',
	job_id: 'job_a',
	label: null,
	service: 'arm-backend'
};

beforeEach(() => {
	fetchJobLogMock.mockReset();
	subscribeMock.mockReset();
	subscribeMock.mockImplementation(() => vi.fn());
});

describe('createJobLog', () => {
	it('load() fetches entries oldest-first and clears error', async () => {
		fetchJobLogMock.mockResolvedValue([ENTRY_A]);
		const log = createJobLog('job_a', { limit: 200 });
		await log.load();
		expect(fetchJobLogMock).toHaveBeenCalledWith('job_a', 200);
		expect(log.entries).toEqual([ENTRY_A]);
		expect(log.error).toBeNull();
		expect(log.loading).toBe(false);
	});

	it('defaults limit to 200', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		const log = createJobLog('job_a', {});
		await log.load();
		expect(fetchJobLogMock).toHaveBeenCalledWith('job_a', 200);
	});

	it('sets error on a failed load', async () => {
		fetchJobLogMock.mockRejectedValue(new Error('boom'));
		const log = createJobLog('job_a', { limit: 200 });
		await log.load();
		expect(log.error).toBeInstanceOf(Error);
		expect(log.entries).toEqual([]);
	});

	it('start() subscribes to logs.{jobId} and sets live true', () => {
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		expect(subscribeMock).toHaveBeenCalledWith('logs.job_a', expect.any(Function));
		expect(log.live).toBe(true);
	});

	it('appends parsed live lines via the log.line handler', () => {
		let handler: (env: WSEnvelope) => void = () => {};
		subscribeMock.mockImplementation((_topic, h) => {
			handler = h;
			return vi.fn();
		});
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		handler(
			logLineEnv('job_a', {
				ts: '2026-09-05T00:00:02Z',
				level: 'warning',
				service: 'arm-ripper-XYZ',
				job_id: 'job_a',
				msg: 'drive slow',
				extra: {}
			})
		);
		expect(log.entries).toHaveLength(1);
		expect(log.entries[0].event).toBe('drive slow');
		expect(log.entries[0].service).toBe('arm-ripper-XYZ');
	});

	it('ignores non log.line events on the same topic', () => {
		let handler: (env: WSEnvelope) => void = () => {};
		subscribeMock.mockImplementation((_topic, h) => {
			handler = h;
			return vi.fn();
		});
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		handler({ ...logLineEnv('job_a', {}), event_type: 'other.event' });
		expect(log.entries).toHaveLength(0);
	});

	it('caps live-appended entries at 2000, dropping the oldest', () => {
		let handler: (env: WSEnvelope) => void = () => {};
		subscribeMock.mockImplementation((_topic, h) => {
			handler = h;
			return vi.fn();
		});
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		for (let i = 0; i < 2005; i++) {
			handler(
				logLineEnv('job_a', {
					ts: `t${i}`,
					level: 'info',
					service: 'arm-backend',
					job_id: 'job_a',
					msg: `line ${i}`,
					extra: {}
				})
			);
		}
		expect(log.entries).toHaveLength(2000);
		expect(log.entries[0].event).toBe('line 5');
		expect(log.entries[1999].event).toBe('line 2004');
	}, 20000);

	it('stop() unsubscribes and sets live false', () => {
		const unsub = vi.fn();
		subscribeMock.mockReturnValue(unsub);
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		log.stop();
		expect(unsub).toHaveBeenCalled();
		expect(log.live).toBe(false);
	});

	it('start() is idempotent (single subscription)', () => {
		const log = createJobLog('job_a', { limit: 200 });
		log.start();
		log.start();
		expect(subscribeMock).toHaveBeenCalledTimes(1);
	});

	it('stop() is idempotent (safe to call when not started)', () => {
		const log = createJobLog('job_a', { limit: 200 });
		expect(() => log.stop()).not.toThrow();
		expect(log.live).toBe(false);
	});

	it('orders the snapshot by timestamp across services, keeping undated lines in place', async () => {
		fetchJobLogMock.mockResolvedValueOnce([
			{ timestamp: '2026-09-05T15:47:01Z', level: 'info', logger: 'x', event: 'backend spawn', service: 'arm-backend' },
			{ timestamp: '2026-09-05T15:46:57Z', level: 'info', logger: 'x', event: 'transcode rename', service: 'arm-transcode-1' },
			{ timestamp: null, level: 'info', logger: 'x', event: 'undated', service: 'arm-ripper-a' }
		] as never);
		const { createJobLog } = await import('../jobLog.svelte');
		const log = createJobLog('job_x', { limit: 10 });
		await log.load();
		expect(log.entries.map((e) => e.event)).toEqual(['transcode rename', 'backend spawn', 'undated']);
	});
});
