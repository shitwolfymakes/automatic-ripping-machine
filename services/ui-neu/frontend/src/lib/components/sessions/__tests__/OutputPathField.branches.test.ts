import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
vi.mock('$lib/api/sessions', () => ({ previewTemplate: vi.fn() }));
import { previewTemplate } from '$lib/api/sessions';
import OutputPathField from '../OutputPathField.svelte';

// Branch pins for OutputPathField, beside OutputPathField.svelte.test.ts. No
// branch is left open.

beforeEach(() => {
	vi.useFakeTimers();
	vi.mocked(previewTemplate).mockReset();
	vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'out.mkv' } as any);
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

describe('OutputPathField preview debounce', () => {
	it('drops the first wait when the template changes again within 300 ms', async () => {
		const view = renderComponent(OutputPathField, { value: 'a/{title}', mediaType: 'movie', onchange: vi.fn() });
		await vi.advanceTimersByTimeAsync(200);
		await view.rerender({ value: 'b/{title}' });
		await vi.advanceTimersByTimeAsync(299);
		expect(previewTemplate).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(previewTemplate).toHaveBeenCalledTimes(1);
		expect(previewTemplate).toHaveBeenCalledWith({ template: 'b/{title}', media_type: 'movie' });
	});
});

describe('OutputPathField preview request body', () => {
	it('sends has_transcode_preset when it is given', async () => {
		renderComponent(OutputPathField, {
			value: 'a/{title}',
			mediaType: 'movie',
			onchange: vi.fn(),
			has_transcode_preset: true
		});
		await vi.advanceTimersByTimeAsync(300);
		expect(previewTemplate).toHaveBeenCalledWith({
			template: 'a/{title}',
			media_type: 'movie',
			has_transcode_preset: true
		});
	});

	it('leaves has_transcode_preset out when it is not given', async () => {
		renderComponent(OutputPathField, { value: 'a/{title}', mediaType: 'movie', onchange: vi.fn() });
		await vi.advanceTimersByTimeAsync(300);
		const body = vi.mocked(previewTemplate).mock.calls[0][0];
		expect(body).toEqual({ template: 'a/{title}', media_type: 'movie' });
		expect('has_transcode_preset' in body).toBe(false);
	});
});

describe('OutputPathField preview rejection', () => {
	it('shows a rejection that is not an Error as its string under PREVIEW ERROR', async () => {
		vi.mocked(previewTemplate).mockRejectedValueOnce('boom');
		renderComponent(OutputPathField, { value: 'a/{title}', mediaType: 'movie', onchange: vi.fn() });
		await vi.advanceTimersByTimeAsync(300);
		expect(screen.getByText('PREVIEW ERROR')).toBeInTheDocument();
		expect(screen.getByText('boom')).toBeInTheDocument();
	});
});
