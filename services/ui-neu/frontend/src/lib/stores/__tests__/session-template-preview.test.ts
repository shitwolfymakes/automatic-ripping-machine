import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
vi.mock('$lib/api/sessions', () => ({ previewTemplate: vi.fn() }));
import { previewTemplate } from '$lib/api/sessions';
import { TemplatePreview } from '../session-template-preview.svelte';

beforeEach(() => {
	vi.useFakeTimers();
	vi.mocked(previewTemplate).mockReset();
	vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'out.mkv' } as any);
});

afterEach(() => {
	vi.useRealTimers();
});

describe('TemplatePreview.schedule', () => {
	it('requests nothing before 300 ms, then sends the request and stores the expansion', async () => {
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(299);
		expect(previewTemplate).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(previewTemplate).toHaveBeenCalledWith({ template: 'a', media_type: 'movie' });
		expect(preview.expansion).toBe('out.mkv');
		expect(preview.expansionWithoutOptional).toBeNull();
		expect(preview.error).toBeNull();
	});

	it('stores the expansion with optional values empty when the response has one', async () => {
		vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'a (2020)', expansion_without_optional: 'a' } as any);
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		expect(preview.expansion).toBe('a (2020)');
		expect(preview.expansionWithoutOptional).toBe('a');
	});

	it('sends only the second request when scheduled again within the wait', async () => {
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(200);
		preview.schedule(() => ({ template: 'b', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		expect(previewTemplate).toHaveBeenCalledTimes(1);
		expect(previewTemplate).toHaveBeenCalledWith({ template: 'b', media_type: 'movie' });
	});

	it('builds the request when the wait ends, not when scheduled', async () => {
		const preview = new TemplatePreview();
		const request = vi.fn(() => ({ template: 'a', media_type: 'movie' as const }));
		preview.schedule(request);
		expect(request).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(300);
		expect(request).toHaveBeenCalledTimes(1);
	});

	it('sets error to an Error message and clears both expansions on a rejection', async () => {
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		vi.mocked(previewTemplate).mockRejectedValue(new Error('bad template'));
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		expect(preview.error).toBe('bad template');
		expect(preview.expansion).toBeNull();
		expect(preview.expansionWithoutOptional).toBeNull();
	});

	it('sets error to the string of a non-Error rejection, and a later success clears it', async () => {
		vi.mocked(previewTemplate).mockRejectedValue('nope');
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		expect(preview.error).toBe('nope');
		vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'ok' } as any);
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		expect(preview.error).toBeNull();
		expect(preview.expansion).toBe('ok');
	});
});

describe('TemplatePreview.cancel', () => {
	it('stops a waiting preview', async () => {
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		preview.cancel();
		await vi.advanceTimersByTimeAsync(500);
		expect(previewTemplate).not.toHaveBeenCalled();
	});
});

describe('TemplatePreview.clear', () => {
	it('resets the expansion, the optional-free expansion and the error', async () => {
		vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'a', expansion_without_optional: 'b' } as any);
		const preview = new TemplatePreview();
		preview.schedule(() => ({ template: 'a', media_type: 'movie' }));
		await vi.advanceTimersByTimeAsync(300);
		preview.error = 'x';
		preview.clear();
		expect(preview.expansion).toBeNull();
		expect(preview.expansionWithoutOptional).toBeNull();
		expect(preview.error).toBeNull();
	});
});
