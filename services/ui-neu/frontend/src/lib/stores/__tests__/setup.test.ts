import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchSetup = vi.fn();
const putSetupStep = vi.fn();
const deferSetup = vi.fn();
vi.mock('$lib/api/setup', () => ({
	fetchSetup: () => fetchSetup(),
	putSetupStep: (s: string, st: string) => putSetupStep(s, st),
	deferSetup: () => deferSetup()
}));

import { setupState, loadSetup, markStep, finishLater } from '../setup.svelte';

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

	it('Finish later defers setup on the server, for every browser', async () => {
		deferSetup.mockResolvedValue({ ...view, deferred: true });
		await finishLater();
		expect(deferSetup).toHaveBeenCalledOnce();
		expect(setupState.view?.deferred).toBe(true);
		// Nothing browser-local: another browser must see the same answer.
		expect(sessionStorage.length).toBe(0);
		expect(localStorage.getItem('arm_setup_finish_later')).toBeNull();
	});

	it('a failed deferral is reported to the caller', async () => {
		deferSetup.mockRejectedValue(new Error('down'));
		await expect(finishLater()).rejects.toThrow('down');
	});
});
