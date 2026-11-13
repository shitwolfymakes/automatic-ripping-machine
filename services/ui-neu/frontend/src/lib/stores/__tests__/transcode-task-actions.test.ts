import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';

vi.mock('$lib/api/transcoder', () => ({
	retryTranscoderJob: vi.fn(),
	deleteTranscoderJob: vi.fn()
}));

import { retryTranscoderJob, deleteTranscoderJob } from '$lib/api/transcoder';
import { TranscodeTaskActions } from '../transcode-task-actions.svelte';

describe('TranscodeTaskActions', () => {
	let reload: Mock<() => void>;
	let actions: TranscodeTaskActions;
	let confirmSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		vi.mocked(retryTranscoderJob)
			.mockReset()
			.mockResolvedValue(undefined as never);
		vi.mocked(deleteTranscoderJob)
			.mockReset()
			.mockResolvedValue(undefined as never);
		reload = vi.fn();
		actions = new TranscodeTaskActions(reload);
		confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
	});

	afterEach(() => {
		confirmSpy.mockRestore();
	});

	it('starts with no error', () => {
		expect(actions.error).toBeNull();
	});

	it('retry succeeds with no error and reloads once', async () => {
		await actions.retry('t1');
		expect(retryTranscoderJob).toHaveBeenCalledWith('t1');
		expect(actions.error).toBeNull();
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it('retry failing with an Error shows its message and still reloads', async () => {
		vi.mocked(retryTranscoderJob).mockRejectedValue(new Error('409 conflict'));
		await actions.retry('t1');
		expect(actions.error).toBe('409 conflict');
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it('retry failing with a non-Error shows "Retry failed" and still reloads', async () => {
		vi.mocked(retryTranscoderJob).mockRejectedValue('nope');
		await actions.retry('t1');
		expect(actions.error).toBe('Retry failed');
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it('clears an earlier error when an action starts', async () => {
		vi.mocked(retryTranscoderJob).mockRejectedValueOnce(new Error('boom'));
		await actions.retry('t1');
		expect(actions.error).toBe('boom');
		await actions.retry('t1');
		expect(actions.error).toBeNull();
	});

	it('remove with the confirm declined sends no request and does not reload', () => {
		confirmSpy.mockReturnValue(false);
		expect(actions.remove('t1')).toBeUndefined();
		expect(confirmSpy).toHaveBeenCalledWith('Delete this transcode task?');
		expect(deleteTranscoderJob).not.toHaveBeenCalled();
		expect(reload).not.toHaveBeenCalled();
	});

	it('remove accepted and succeeding deletes and reloads once', async () => {
		await actions.remove('t1');
		expect(deleteTranscoderJob).toHaveBeenCalledWith('t1');
		expect(actions.error).toBeNull();
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it('remove failing with a non-Error shows "Delete failed"', async () => {
		vi.mocked(deleteTranscoderJob).mockRejectedValue('nope');
		await actions.remove('t1');
		expect(actions.error).toBe('Delete failed');
		expect(reload).toHaveBeenCalledTimes(1);
	});

	it('dismiss clears the error', async () => {
		vi.mocked(retryTranscoderJob).mockRejectedValue(new Error('boom'));
		await actions.retry('t1');
		actions.dismiss();
		expect(actions.error).toBeNull();
	});
});
