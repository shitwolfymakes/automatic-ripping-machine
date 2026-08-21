import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// getToken gates connect(); give it a token so the socket opens.
vi.mock('$lib/api/client', () => ({
	getToken: () => 'aaa.bbb.ccc'
}));

import { wsClient, type WSEnvelope } from '$lib/api/ws';

// Minimal fake WebSocket capturing sends + exposing the listener hooks so the
// test can drive open/message/close.
class FakeWS {
	static instances: FakeWS[] = [];
	url: string;
	sent: string[] = [];
	private listeners: Record<string, ((ev: { data?: unknown }) => void)[]> = {};
	constructor(url: string) {
		this.url = url;
		FakeWS.instances.push(this);
	}
	addEventListener(type: string, fn: (ev: { data?: unknown }) => void) {
		(this.listeners[type] ??= []).push(fn);
	}
	send(data: string) {
		this.sent.push(data);
	}
	close() {
		this.emit('close', {});
	}
	emit(type: string, ev: { data?: unknown }) {
		for (const fn of this.listeners[type] ?? []) fn(ev);
	}
}

function authAck(ws: FakeWS) {
	// open → client sends auth; then the server's auth ack flips `connected`.
	ws.emit('open', {});
	ws.emit('message', { data: JSON.stringify({ op: 'ack', topic: '' }) });
}

describe('wsClient', () => {
	beforeEach(() => {
		FakeWS.instances = [];
		vi.stubGlobal('WebSocket', FakeWS as unknown as typeof WebSocket);
		vi.stubGlobal('window', {
			location: { protocol: 'https:', host: 'localhost:8888' }
		} as unknown as Window & typeof globalThis);
	});

	afterEach(() => {
		wsClient.stop();
		vi.unstubAllGlobals();
	});

	it('connects to the same-origin /ws and authenticates on open', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		expect(ws.url).toBe('wss://localhost:8888/ws');
		ws.emit('open', {});
		expect(JSON.parse(ws.sent[0])).toEqual({ op: 'auth', token: 'aaa.bbb.ccc' });
	});

	it('sends subscribe after the auth ack and delivers events to the handler', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		const handler = vi.fn();
		wsClient.subscribe('ripper.progress.job_a', handler);
		authAck(ws);
		// auth ack replays the subscription
		expect(ws.sent.some((s) => s.includes('"op":"subscribe"') && s.includes('ripper.progress.job_a'))).toBe(true);

		const env: WSEnvelope = {
			op: 'event',
			event_id: 'e1',
			event_type: 'ripper.progress',
			emitted_at: 'now',
			topic: 'ripper.progress.job_a',
			job_id: 'job_a',
			track_id: 'trk_1',
			payload: { track_id: 'trk_1', progress_pct: 42 }
		};
		ws.emit('message', { data: JSON.stringify(env) });
		expect(handler).toHaveBeenCalledWith(expect.objectContaining({ topic: 'ripper.progress.job_a' }));
	});

	it('unsubscribing the last handler sends an unsubscribe', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		const off = wsClient.subscribe('ripper.events', vi.fn());
		authAck(ws);
		off();
		expect(ws.sent.some((s) => s.includes('"op":"unsubscribe"') && s.includes('ripper.events'))).toBe(true);
	});

	it('does not deliver events for unsubscribed topics', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		const handler = vi.fn();
		wsClient.subscribe('ripper.progress.job_a', handler);
		authAck(ws);
		ws.emit('message', {
			data: JSON.stringify({ op: 'event', topic: 'ripper.progress.OTHER', payload: {} })
		});
		expect(handler).not.toHaveBeenCalled();
	});

	it('a throwing handler does not poison the demux loop', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		const bad = vi.fn(() => {
			throw new Error('boom');
		});
		const good = vi.fn();
		wsClient.subscribe('ripper.events', bad);
		wsClient.subscribe('ripper.events', good);
		authAck(ws);
		vi.spyOn(console, 'error').mockImplementation(() => {});
		ws.emit('message', { data: JSON.stringify({ op: 'event', topic: 'ripper.events', payload: {} }) });
		expect(bad).toHaveBeenCalled();
		expect(good).toHaveBeenCalled();
	});

	it('ignores non-JSON and non-event frames', () => {
		wsClient.start();
		const ws = FakeWS.instances[0];
		const handler = vi.fn();
		wsClient.subscribe('ripper.events', handler);
		authAck(ws);
		ws.emit('message', { data: 'not json' });
		ws.emit('message', { data: JSON.stringify({ op: 'something-else' }) });
		expect(handler).not.toHaveBeenCalled();
	});
});
