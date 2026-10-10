import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

describe('config store', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.restoreAllMocks();
	});

	it('defaults to transcoderEnabled=true and transcodeRuntimeEnabled=true before hydration', async () => {
		const { transcoderEnabled, transcodeRuntimeEnabled } = await import('../config');
		expect(get(transcoderEnabled)).toBe(true);
		expect(get(transcodeRuntimeEnabled)).toBe(true);
	});

	it('setTranscoderEnabled updates store', async () => {
		const { transcoderEnabled, setTranscoderEnabled } = await import('../config');
		setTranscoderEnabled(false);
		expect(get(transcoderEnabled)).toBe(false);
		setTranscoderEnabled(true);
		expect(get(transcoderEnabled)).toBe(true);
	});

	it('setTranscodeRuntimeEnabled updates store', async () => {
		const { transcodeRuntimeEnabled, setTranscodeRuntimeEnabled } = await import('../config');
		setTranscodeRuntimeEnabled(false);
		expect(get(transcodeRuntimeEnabled)).toBe(false);
		setTranscodeRuntimeEnabled(true);
		expect(get(transcodeRuntimeEnabled)).toBe(true);
	});

	it('hydrateConfig: capable=false hides regardless of enabled', async () => {
		globalThis.fetch = vi.fn().mockResolvedValueOnce({
			ok: true,
			json: async () => ({ transcode_capable: false, transcode_enabled: true })
		}) as unknown as typeof fetch;

		const { transcoderEnabled, transcodeRuntimeEnabled, hydrateConfig } = await import('../config');
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(false);
		expect(get(transcodeRuntimeEnabled)).toBe(false);
	});

	it('hydrateConfig: capable=true + enabled=false gives transcoderEnabled true, transcodeRuntimeEnabled false', async () => {
		globalThis.fetch = vi.fn().mockResolvedValueOnce({
			ok: true,
			json: async () => ({ transcode_capable: true, transcode_enabled: false })
		}) as unknown as typeof fetch;

		const { transcoderEnabled, transcodeRuntimeEnabled, hydrateConfig } = await import('../config');
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(true);
		expect(get(transcodeRuntimeEnabled)).toBe(false);
	});

	it('hydrateConfig: capable=true + enabled=true gives both true', async () => {
		globalThis.fetch = vi.fn().mockResolvedValueOnce({
			ok: true,
			json: async () => ({ transcode_capable: true, transcode_enabled: true })
		}) as unknown as typeof fetch;

		const { transcoderEnabled, transcodeRuntimeEnabled, hydrateConfig } = await import('../config');
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(true);
		expect(get(transcodeRuntimeEnabled)).toBe(true);
	});

	it('hydrateConfig falls back to true for both flags on fetch failure', async () => {
		globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('network')) as unknown as typeof fetch;

		const { transcoderEnabled, transcodeRuntimeEnabled, hydrateConfig, setTranscoderEnabled, setTranscodeRuntimeEnabled } =
			await import('../config');
		setTranscoderEnabled(false);
		setTranscodeRuntimeEnabled(false);
		await hydrateConfig();
		expect(get(transcoderEnabled)).toBe(true);
		expect(get(transcodeRuntimeEnabled)).toBe(true);
	});
});
