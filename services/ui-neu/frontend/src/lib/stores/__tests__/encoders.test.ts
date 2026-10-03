import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { WSEnvelope } from '$lib/api/ws';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';

const ws = vi.hoisted(() => ({
	start: vi.fn(),
	unsubscribe: vi.fn(),
	subscribe: vi.fn(),
	handler: null as ((env: WSEnvelope) => void) | null
}));
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: () => ws.start(),
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => {
			ws.handler = handler;
			ws.subscribe(topic, handler);
			return ws.unsubscribe;
		}
	}
}));

function transcodeEvent(eventType: string): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: eventType,
		emitted_at: 'now',
		topic: 'transcode.events',
		job_id: null,
		track_id: null,
		payload: { gpu_id: 'gpu_1' }
	};
}

function deferred<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
	let resolve!: (v: T) => void;
	const promise = new Promise<T>((r) => (resolve = r));
	return { promise, resolve };
}

const CATALOG: EncoderAvailabilityView[] = [
	{
		id: 'preset',
		label: "HandBrake preset's own encoder",
		group: 'preset',
		engine: 'handbrake',
		kind: 'preset',
		vendor: null,
		codec: null,
		available: true,
		reason: null
	},
	{
		id: 'any_h265',
		label: 'Any GPU H.265',
		group: 'any',
		engine: 'handbrake',
		kind: 'any',
		vendor: null,
		codec: 'h265',
		available: true,
		reason: null
	}
];

describe('encoders store', () => {
	let stopEvents: (() => void) | null = null;

	beforeEach(() => {
		vi.resetModules();
		vi.restoreAllMocks();
		ws.start.mockReset();
		ws.subscribe.mockReset();
		ws.unsubscribe.mockReset();
		ws.handler = null;
	});

	afterEach(() => {
		stopEvents?.();
		stopEvents = null;
	});

	async function importStore() {
		const mod = await import('../encoders.svelte');
		stopEvents = mod.stopEncoderEvents;
		return mod;
	}

	it('starts empty, not loading, no error', async () => {
		const { encodersStore } = await importStore();
		expect(encodersStore.list).toEqual([]);
		expect(encodersStore.loading).toBe(false);
		expect(encodersStore.error).toBeNull();
	});

	it('load() populates the cache from fetchEncoders and clears loading', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore } = await importStore();

		const p = encodersStore.load();
		expect(encodersStore.loading).toBe(true);
		await p;

		expect(encodersStore.loading).toBe(false);
		expect(encodersStore.error).toBeNull();
		expect(encodersStore.list).toEqual(CATALOG);
	});

	it('concurrent load() calls share one fetch', async () => {
		const fetchMock = vi.fn(() => Promise.resolve(CATALOG));
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await Promise.all([encodersStore.load(), encodersStore.load(), encodersStore.load()]);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('a cache hit skips a second fetch', async () => {
		const fetchMock = vi.fn(() => Promise.resolve(CATALOG));
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await encodersStore.load();
		await encodersStore.load();
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('a failed load sets error, leaves the cache empty, and a later call retries', async () => {
		const fetchMock = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(CATALOG);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await encodersStore.load();
		expect(encodersStore.error).not.toBeNull();
		expect(encodersStore.list).toEqual([]);
		expect(encodersStore.loading).toBe(false);

		await encodersStore.load();
		expect(fetchMock).toHaveBeenCalledTimes(2);
		expect(encodersStore.error).toBeNull();
		expect(encodersStore.list).toEqual(CATALOG);
	});

	it('refresh() refetches even when the cache is populated, without a loading flash', async () => {
		const updated = CATALOG.map((e) => (e.id === 'any_h265' ? { ...e, reason: 'no verified GPU' } : e));
		const fetchMock = vi.fn().mockResolvedValueOnce(CATALOG).mockResolvedValueOnce(updated);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await encodersStore.load();
		const p = encodersStore.refresh();
		expect(encodersStore.loading).toBe(false);
		await p;

		expect(fetchMock).toHaveBeenCalledTimes(2);
		expect(encodersStore.list).toEqual(updated);
	});

	it('a load() joining a running refresh() shares it without a follow-up', async () => {
		const fetchMock = vi.fn(() => Promise.resolve(CATALOG));
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await Promise.all([encodersStore.refresh(), encodersStore.load()]);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('a refresh() during a running fetch runs one follow-up fetch whose result wins', async () => {
		const updated = CATALOG.map((e) => (e.id === 'any_h265' ? { ...e, reason: null, label: 'After probe' } : e));
		const first = deferred<EncoderAvailabilityView[]>();
		const fetchMock = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(updated);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		const loading = encodersStore.load();
		const joined = encodersStore.refresh();
		first.resolve(CATALOG);
		await Promise.all([loading, joined]);

		expect(fetchMock).toHaveBeenCalledTimes(2);
		expect(encodersStore.list).toEqual(updated);
	});

	it('N refresh() calls during one running fetch queue exactly one follow-up', async () => {
		const first = deferred<EncoderAvailabilityView[]>();
		const fetchMock = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(CATALOG);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		const running = encodersStore.refresh();
		const joined = [encodersStore.refresh(), encodersStore.refresh(), encodersStore.refresh()];
		first.resolve(CATALOG);
		await Promise.all([running, ...joined]);

		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('the first refresh() subscribes once to transcode.events; load() does not', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore } = await importStore();

		await encodersStore.load();
		expect(ws.subscribe).not.toHaveBeenCalled();

		await encodersStore.refresh();
		await encodersStore.refresh();
		expect(ws.start).toHaveBeenCalledTimes(1);
		expect(ws.subscribe).toHaveBeenCalledTimes(1);
		expect(ws.subscribe).toHaveBeenCalledWith('transcode.events', expect.any(Function));
	});

	it('a gpu.probed event refetches availability; other transcode events do not', async () => {
		const updated = CATALOG.map((e) => (e.id === 'any_h265' ? { ...e, reason: 'no verified GPU' } : e));
		const fetchMock = vi.fn().mockResolvedValueOnce(CATALOG).mockResolvedValueOnce(updated);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await encodersStore.refresh();
		ws.handler?.(transcodeEvent('transcode.progress'));
		expect(fetchMock).toHaveBeenCalledTimes(1);

		ws.handler?.(transcodeEvent('gpu.probed'));
		await vi.waitFor(() => expect(encodersStore.list).toEqual(updated));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('stopEncoderEvents() unsubscribes, and a later refresh() subscribes again', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore, stopEncoderEvents } = await importStore();

		await encodersStore.refresh();
		stopEncoderEvents();
		expect(ws.unsubscribe).toHaveBeenCalledTimes(1);
		stopEncoderEvents();
		expect(ws.unsubscribe).toHaveBeenCalledTimes(1);

		await encodersStore.refresh();
		expect(ws.subscribe).toHaveBeenCalledTimes(2);
	});

	it('a failed refresh keeps the cached list and sets error', async () => {
		const fetchMock = vi.fn().mockResolvedValueOnce(CATALOG).mockRejectedValueOnce(new Error('network'));
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await importStore();

		await encodersStore.load();
		await encodersStore.refresh();
		expect(encodersStore.list).toEqual(CATALOG);
		expect(encodersStore.error).not.toBeNull();
	});

	it('encoderLabel: empty for the tool-own encoder, null and undefined', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encoderLabel } = await importStore();
		expect(encoderLabel('preset')).toBe('');
		expect(encoderLabel(null)).toBe('');
		expect(encoderLabel(undefined)).toBe('');
	});

	it('encoderLabel: the catalog label once loaded, the raw id otherwise', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore, encoderLabel } = await importStore();

		// Before the cache has loaded: falls back to the raw id.
		expect(encoderLabel('any_h265')).toBe('any_h265');
		// An id the catalog doesn't know, even once loaded: still the raw id.
		await encodersStore.load();
		expect(encoderLabel('any_h265')).toBe('Any GPU H.265');
		expect(encoderLabel('future_x')).toBe('future_x');
	});
});
