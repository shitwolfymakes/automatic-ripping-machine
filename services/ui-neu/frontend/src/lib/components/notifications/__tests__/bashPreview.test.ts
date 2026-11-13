import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import type { BashPreviewRequest } from '$lib/api/channels';
import { BashPreview } from '../../../notifications/bash-preview.svelte';
import { failedPreview, failedRun } from '../../../notifications/bash-results';

const previewBash = vi.fn();
vi.mock('$lib/api/channels', async (orig) => ({
	...(await orig<typeof import('$lib/api/channels')>()),
	previewBash: (...a: unknown[]) => previewBash(...a)
}));

const body = (event_type: string) =>
	({ config: {}, event_type, template: null, channel_id: null, run: false }) as never as BashPreviewRequest;
const okResult = { ok: true, exit_code: 0, duration_ms: 5, stdout: 'o', stderr: '', error: null };
const preview = { title: 't', body: 'b', inputs: {}, env: {}, argv: [], error: null, result: null };

describe('BashPreview', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		previewBash.mockReset();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	describe('schedule', () => {
		it('sends nothing before 300 ms and stores the preview after', async () => {
			previewBash.mockResolvedValue(preview);
			const p = new BashPreview();
			p.schedule(() => body('a'));
			await vi.advanceTimersByTimeAsync(299);
			expect(previewBash).not.toHaveBeenCalled();
			expect(p.preview).toBeNull();
			await vi.advanceTimersByTimeAsync(1);
			expect(previewBash).toHaveBeenCalledWith(body('a'));
			expect(p.preview).toEqual(preview);
		});

		it('sends only the second request when scheduled again within the wait', async () => {
			previewBash.mockResolvedValue(preview);
			const p = new BashPreview();
			p.schedule(() => body('first'));
			await vi.advanceTimersByTimeAsync(200);
			p.schedule(() => body('second'));
			await vi.advanceTimersByTimeAsync(300);
			expect(previewBash).toHaveBeenCalledTimes(1);
			expect(previewBash).toHaveBeenCalledWith(body('second'));
		});

		it('builds the request when the wait ends, not when scheduled', async () => {
			previewBash.mockResolvedValue(preview);
			const p = new BashPreview();
			const request = vi.fn(() => body('a'));
			p.schedule(request);
			expect(request).not.toHaveBeenCalled();
			await vi.advanceTimersByTimeAsync(300);
			expect(request).toHaveBeenCalledTimes(1);
		});

		it('stores a failed preview with the message of an Error rejection', async () => {
			previewBash.mockRejectedValue(new Error('boom'));
			const p = new BashPreview();
			p.schedule(() => body('a'));
			await vi.advanceTimersByTimeAsync(300);
			expect(p.preview).toEqual(failedPreview('boom'));
		});

		it('stores a failed preview with a fixed message for any other rejection', async () => {
			previewBash.mockRejectedValue('nope');
			const p = new BashPreview();
			p.schedule(() => body('a'));
			await vi.advanceTimersByTimeAsync(300);
			expect(p.preview).toEqual(failedPreview('preview failed'));
		});
	});

	describe('cancel', () => {
		it('never sends a preview that was waiting', async () => {
			const p = new BashPreview();
			p.schedule(() => body('a'));
			p.cancel();
			await vi.advanceTimersByTimeAsync(1000);
			expect(previewBash).not.toHaveBeenCalled();
		});

		it('does nothing when nothing is waiting', () => {
			const p = new BashPreview();
			expect(() => p.cancel()).not.toThrow();
			expect(p.preview).toBeNull();
		});
	});

	describe('run', () => {
		it('is running while the call is in flight and not after, on success', async () => {
			let resolve!: (v: unknown) => void;
			previewBash.mockReturnValue(new Promise((r) => (resolve = r)));
			const p = new BashPreview();
			const done = p.run(body('a'));
			expect(p.running).toBe(true);
			resolve({ ...preview, result: okResult });
			await done;
			expect(p.running).toBe(false);
		});

		it('stores the result as lastRun and the preview as preview', async () => {
			const res = { ...preview, result: okResult };
			previewBash.mockResolvedValue(res);
			const p = new BashPreview();
			await p.run(body('a'));
			expect(previewBash).toHaveBeenCalledWith(body('a'));
			expect(p.lastRun).toEqual(okResult);
			expect(p.preview).toEqual(res);
		});

		it('stores lastRun as null when the response has no result', async () => {
			previewBash.mockResolvedValue({ ...preview, result: undefined });
			const p = new BashPreview();
			await p.run(body('a'));
			expect(p.lastRun).toBeNull();
		});

		it('stores a failed run with the message of an Error rejection and keeps the preview', async () => {
			previewBash.mockRejectedValue(new Error('boom'));
			const p = new BashPreview();
			p.preview = preview;
			await p.run(body('a'));
			expect(p.lastRun).toEqual(failedRun('boom'));
			expect(p.preview).toEqual(preview);
			expect(p.running).toBe(false);
		});

		it('stores a failed run with a fixed message for any other rejection', async () => {
			previewBash.mockRejectedValue('nope');
			const p = new BashPreview();
			await p.run(body('a'));
			expect(p.lastRun).toEqual(failedRun('test failed'));
			expect(p.running).toBe(false);
		});
	});
});
