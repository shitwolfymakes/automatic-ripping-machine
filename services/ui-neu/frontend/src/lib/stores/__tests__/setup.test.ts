import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchSetup = vi.fn();
const putSetupStep = vi.fn();
vi.mock('$lib/api/setup', () => ({
	fetchSetup: () => fetchSetup(),
	putSetupStep: (s: string, st: string) => putSetupStep(s, st)
}));

import { setupState, loadSetup, markStep, finishLater, finishLaterActive, clearFinishLater } from '../setup.svelte';

const view = {
	completed_at: null,
	progress: {},
	current_step: 'account',
	admin_default_password: true,
	checklist_dismissed: false
};

describe('setup store', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
	});

	it('loads and records the view', async () => {
		fetchSetup.mockResolvedValue(view);
		expect(await loadSetup()).toEqual(view);
		expect(setupState.view).toEqual(view);
		expect(setupState.loading).toBe(false);
	});

	it('records a load failure', async () => {
		fetchSetup.mockRejectedValue(new Error('down'));
		await expect(loadSetup()).rejects.toThrow('down');
		expect(setupState.error).toBe('down');
	});

	it('marks a step and keeps the returned view', async () => {
		putSetupStep.mockResolvedValue({ ...view, current_step: 'system' });
		await markStep('account', 'done');
		expect(putSetupStep).toHaveBeenCalledWith('account', 'done');
		expect(setupState.view?.current_step).toBe('system');
	});

	it('Finish later lasts for the browser session', () => {
		expect(finishLaterActive()).toBe(false);
		finishLater();
		expect(finishLaterActive()).toBe(true);
		clearFinishLater();
		expect(finishLaterActive()).toBe(false);
	});
});
