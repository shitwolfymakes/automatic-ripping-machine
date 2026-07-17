import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

describe('config store', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.restoreAllMocks();
	});

	it('defaults to transcoderEnabled=true before hydration', async () => {
		const { transcoderEnabled } = await import('../config');
		expect(get(transcoderEnabled)).toBe(true);
	});

	it('setTranscoderEnabled updates store', async () => {
		const { transcoderEnabled, setTranscoderEnabled } = await import('../config');
		setTranscoderEnabled(false);
		expect(get(transcoderEnabled)).toBe(false);
		setTranscoderEnabled(true);
		expect(get(transcoderEnabled)).toBe(true);
	});

	it('hydrateConfig calls /api/config and keeps transcoder always enabled in v3', async () => {
		// The transcoder subsystem is ALWAYS present in v3, so fetchConfig maps to
		// transcoder_enabled=true regardless of the auto_transcode_on_idle policy.
		globalThis.fetch = vi.fn().mockResolvedValueOnce({
			ok: true,
			json: async () => ({ auto_transcode_on_idle: false })
		}) as unknown as typeof fetch;

		const { transcoderEnabled, hydrateConfig, setTranscoderEnabled } = await import('../config');
		setTranscoderEnabled(false);
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(true);
	});

	it('hydrateConfig falls back to true on fetch failure', async () => {
		globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('network')) as unknown as typeof fetch;

		const { transcoderEnabled, hydrateConfig, setTranscoderEnabled } = await import('../config');
		setTranscoderEnabled(false);
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(true);
	});
});
