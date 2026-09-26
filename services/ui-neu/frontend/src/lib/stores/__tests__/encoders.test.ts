import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';

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
	beforeEach(() => {
		vi.resetModules();
		vi.restoreAllMocks();
	});

	it('starts empty, not loading, no error', async () => {
		const { encodersStore } = await import('../encoders.svelte');
		expect(encodersStore.list).toEqual([]);
		expect(encodersStore.loading).toBe(false);
		expect(encodersStore.error).toBeNull();
	});

	it('load() populates the cache from fetchEncoders and clears loading', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore } = await import('../encoders.svelte');

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
		const { encodersStore } = await import('../encoders.svelte');

		await Promise.all([encodersStore.load(), encodersStore.load(), encodersStore.load()]);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('a cache hit skips a second fetch', async () => {
		const fetchMock = vi.fn(() => Promise.resolve(CATALOG));
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await import('../encoders.svelte');

		await encodersStore.load();
		await encodersStore.load();
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('a failed load sets error, leaves the cache empty, and a later call retries', async () => {
		const fetchMock = vi
			.fn()
			.mockRejectedValueOnce(new Error('network'))
			.mockResolvedValueOnce(CATALOG);
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: fetchMock }));
		const { encodersStore } = await import('../encoders.svelte');

		await encodersStore.load();
		expect(encodersStore.error).not.toBeNull();
		expect(encodersStore.list).toEqual([]);
		expect(encodersStore.loading).toBe(false);

		await encodersStore.load();
		expect(fetchMock).toHaveBeenCalledTimes(2);
		expect(encodersStore.error).toBeNull();
		expect(encodersStore.list).toEqual(CATALOG);
	});

	it('encoderLabel: empty for the tool-own encoder, null and undefined', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encoderLabel } = await import('../encoders.svelte');
		expect(encoderLabel('preset')).toBe('');
		expect(encoderLabel(null)).toBe('');
		expect(encoderLabel(undefined)).toBe('');
	});

	it('encoderLabel: the catalog label once loaded, the raw id otherwise', async () => {
		vi.doMock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(CATALOG) }));
		const { encodersStore, encoderLabel } = await import('../encoders.svelte');

		// Before the cache has loaded: falls back to the raw id.
		expect(encoderLabel('any_h265')).toBe('any_h265');
		// An id the catalog doesn't know, even once loaded: still the raw id.
		await encodersStore.load();
		expect(encoderLabel('any_h265')).toBe('Any GPU H.265');
		expect(encoderLabel('future_x')).toBe('future_x');
	});
});
