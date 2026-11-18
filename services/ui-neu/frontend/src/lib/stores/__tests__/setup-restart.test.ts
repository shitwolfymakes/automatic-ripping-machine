import { describe, it, expect, vi, beforeEach } from 'vitest';

const restartSetupMock = vi.fn();
const gotoMock = vi.fn();
vi.mock('$lib/api/setup', () => ({
	restartSetup: (...a: unknown[]) => restartSetupMock(...a)
}));
vi.mock('$app/navigation', () => ({
	goto: (...a: unknown[]) => gotoMock(...a)
}));

import { SetupRestart } from '$lib/stores/setup-restart.svelte';

beforeEach(() => {
	restartSetupMock.mockReset();
	gotoMock.mockReset();
});

describe('SetupRestart', () => {
	it('starts idle', () => {
		expect(new SetupRestart().running).toBe(false);
	});

	it('is running while the request is pending', async () => {
		let resolve!: () => void;
		restartSetupMock.mockReturnValue(new Promise<void>((r) => (resolve = r)));
		const restart = new SetupRestart();
		const pending = restart.run();
		expect(restart.running).toBe(true);
		expect(gotoMock).not.toHaveBeenCalled();
		resolve();
		await pending;
	});

	it('navigates to the setup wizard and clears running on success', async () => {
		restartSetupMock.mockResolvedValue(undefined);
		const restart = new SetupRestart();
		await restart.run();
		expect(gotoMock).toHaveBeenCalledWith('/setup/system');
		expect(restart.running).toBe(false);
	});

	it('shows the request error, stays put and clears running on failure', async () => {
		restartSetupMock.mockRejectedValue(new Error('boom'));
		const restart = new SetupRestart();
		await restart.run();
		expect(restart.feedback.current).toEqual({ type: 'error', message: 'boom' });
		expect(gotoMock).not.toHaveBeenCalled();
		expect(restart.running).toBe(false);
	});

	it('shows the fallback message when the failure is not an Error', async () => {
		restartSetupMock.mockRejectedValue('nope');
		const restart = new SetupRestart();
		await restart.run();
		expect(restart.feedback.current).toEqual({ type: 'error', message: 'Could not restart setup' });
	});

	it('clears an earlier error when it runs again', async () => {
		restartSetupMock.mockRejectedValueOnce(new Error('boom'));
		const restart = new SetupRestart();
		await restart.run();
		let resolve!: () => void;
		restartSetupMock.mockReturnValue(new Promise<void>((r) => (resolve = r)));
		const pending = restart.run();
		expect(restart.feedback.current).toBeNull();
		resolve();
		await pending;
	});
});
