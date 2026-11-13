import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const fetchGpusMock = vi.fn();
vi.mock('$lib/api/gpus', () => ({
	fetchGpus: (...a: unknown[]) => fetchGpusMock(...a)
}));

const startMock = vi.fn();
const unsubscribeMock = vi.fn();
let handler: (() => void) | null = null;
const subscribeMock = vi.fn((_topic: string, h: () => void) => {
	handler = h;
	return unsubscribeMock;
});
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: () => startMock(),
		subscribe: (topic: string, h: () => void) => subscribeMock(topic, h)
	}
}));

import { GpuInventory } from '$lib/stores/gpu-inventory.svelte';

const GPU = { id: 'gpu-0' };

beforeEach(() => {
	vi.useFakeTimers();
	fetchGpusMock.mockReset();
	fetchGpusMock.mockResolvedValue([GPU]);
	startMock.mockClear();
	unsubscribeMock.mockClear();
	subscribeMock.mockClear();
	handler = null;
});

afterEach(() => {
	vi.useRealTimers();
});

describe('GpuInventory', () => {
	it('starts with no rows', () => {
		expect(new GpuInventory().rows).toEqual([]);
	});

	it('load fills the rows from the API', async () => {
		const gpus = new GpuInventory();
		await gpus.load();
		expect(gpus.rows).toEqual([GPU]);
	});

	it('load empties the rows when the fetch fails', async () => {
		const gpus = new GpuInventory();
		await gpus.load();
		fetchGpusMock.mockRejectedValue(new Error('down'));
		await gpus.load();
		expect(gpus.rows).toEqual([]);
	});

	it('watch starts the client and subscribes to transcode.events', () => {
		new GpuInventory().watch();
		expect(startMock).toHaveBeenCalledTimes(1);
		expect(subscribeMock).toHaveBeenCalledWith('transcode.events', expect.any(Function));
	});

	it('reloads 300 ms after an event and not before', async () => {
		new GpuInventory().watch();
		handler!();
		await vi.advanceTimersByTimeAsync(299);
		expect(fetchGpusMock).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(fetchGpusMock).toHaveBeenCalledTimes(1);
	});

	it('reloads once for two events within 300 ms', async () => {
		new GpuInventory().watch();
		handler!();
		await vi.advanceTimersByTimeAsync(200);
		handler!();
		await vi.advanceTimersByTimeAsync(299);
		expect(fetchGpusMock).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(fetchGpusMock).toHaveBeenCalledTimes(1);
	});

	it('the cleanup unsubscribes and clears a pending reload', async () => {
		const stop = new GpuInventory().watch();
		handler!();
		stop();
		expect(unsubscribeMock).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1000);
		expect(fetchGpusMock).not.toHaveBeenCalled();
	});

	it('the cleanup unsubscribes when no reload is pending', async () => {
		const stop = new GpuInventory().watch();
		handler!();
		await vi.advanceTimersByTimeAsync(300);
		fetchGpusMock.mockClear();
		stop();
		expect(unsubscribeMock).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1000);
		expect(fetchGpusMock).not.toHaveBeenCalled();
	});
});
