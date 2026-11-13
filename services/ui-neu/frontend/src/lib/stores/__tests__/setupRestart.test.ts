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

	it('rejects with the request error, stays put and clears running on failure', async () => {
		const error = new Error('boom');
		restartSetupMock.mockRejectedValue(error);
		const restart = new SetupRestart();
		await expect(restart.run()).rejects.toBe(error);
		expect(gotoMock).not.toHaveBeenCalled();
		expect(restart.running).toBe(false);
	});
});
