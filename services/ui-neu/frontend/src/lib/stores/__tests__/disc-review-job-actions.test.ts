import { describe, it, expect, vi, beforeEach } from 'vitest';

const abandonJobMock = vi.fn();
const deleteJobMock = vi.fn();
const startWaitingJobMock = vi.fn();
const pauseWaitingJobMock = vi.fn();
const resolveJobMock = vi.fn();
const cancelIsoRipMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	abandonJob: (...a: unknown[]) => abandonJobMock(...a),
	deleteJob: (...a: unknown[]) => deleteJobMock(...a),
	startWaitingJob: (...a: unknown[]) => startWaitingJobMock(...a),
	pauseWaitingJob: (...a: unknown[]) => pauseWaitingJobMock(...a),
	resolveJob: (...a: unknown[]) => resolveJobMock(...a)
}));
vi.mock('$lib/api/iso', () => ({
	cancelIsoRip: (...a: unknown[]) => cancelIsoRipMock(...a)
}));

import { DiscReviewJobActions } from '$lib/stores/disc-review-job-actions.svelte';
import { createJob } from '../../__fixtures__/job';

const calls: string[] = [];
const dismiss = vi.fn(() => calls.push('dismiss'));
const refresh = vi.fn(() => calls.push('refresh'));

function make() {
	return new DiscReviewJobActions({ dismiss, refresh });
}

function deferred() {
	let resolve!: () => void;
	const promise = new Promise<void>((r) => (resolve = r));
	return { promise, resolve };
}

beforeEach(() => {
	for (const m of [
		abandonJobMock,
		deleteJobMock,
		startWaitingJobMock,
		pauseWaitingJobMock,
		resolveJobMock,
		cancelIsoRipMock,
		dismiss,
		refresh
	]) {
		m.mockReset();
	}
	calls.length = 0;
	dismiss.mockImplementation(() => calls.push('dismiss'));
	refresh.mockImplementation(() => calls.push('refresh'));
});

function expectIdle(a: DiscReviewJobActions) {
	expect(a.cancelling).toBe(false);
	expect(a.deleting).toBe(false);
	expect(a.starting).toBe(false);
	expect(a.pauseBusy).toBe(false);
	expect(a.confirmDelete).toBe(false);
	expect(a.errorMessage).toBeNull();
	expect(dismiss).not.toHaveBeenCalled();
	expect(refresh).not.toHaveBeenCalled();
}

describe('DiscReviewJobActions', () => {
	it('starts idle with no error', () => {
		expectIdle(make());
	});

	it('dismissError clears the message', () => {
		const a = make();
		a.errorMessage = 'boom';
		a.dismissError();
		expect(a.errorMessage).toBeNull();
	});

	describe('cancel', () => {
		it('does nothing without a job', async () => {
			const a = make();
			await a.cancel(undefined, null);
			expect(abandonJobMock).not.toHaveBeenCalled();
			expect(cancelIsoRipMock).not.toHaveBeenCalled();
			expectIdle(a);
		});

		it('abandons the job, then dismisses and refreshes, with the flag up while pending', async () => {
			const d = deferred();
			abandonJobMock.mockReturnValue(d.promise);
			const a = make();
			a.errorMessage = 'old';
			const p = a.cancel(createJob({ id: 'j1' }), null);
			expect(a.cancelling).toBe(true);
			expect(a.errorMessage).toBeNull();
			d.resolve();
			await p;
			expect(abandonJobMock).toHaveBeenCalledWith('j1');
			expect(calls).toEqual(['dismiss', 'refresh']);
			expect(a.cancelling).toBe(false);
		});

		it('cancels the ISO rip by drive for an ISO name with a drive_id', async () => {
			cancelIsoRipMock.mockResolvedValue(undefined);
			await make().cancel(createJob({ id: 'j1', drive_id: 'drv_9' }), 'disc.iso');
			expect(cancelIsoRipMock).toHaveBeenCalledWith('drv_9');
			expect(abandonJobMock).not.toHaveBeenCalled();
		});

		it('abandons the job for an ISO name without a drive_id', async () => {
			abandonJobMock.mockResolvedValue(undefined);
			await make().cancel(createJob({ id: 'j1', drive_id: null }), 'disc.iso');
			expect(abandonJobMock).toHaveBeenCalledWith('j1');
			expect(cancelIsoRipMock).not.toHaveBeenCalled();
		});

		it('shows an Error failure message', async () => {
			abandonJobMock.mockRejectedValue(new Error('nope'));
			const a = make();
			await a.cancel(createJob(), null);
			expect(a.errorMessage).toBe('nope');
			expect(a.cancelling).toBe(false);
			expect(calls).toEqual([]);
		});

		it('shows the fallback for a non-Error failure', async () => {
			abandonJobMock.mockRejectedValue('x');
			const a = make();
			await a.cancel(createJob(), null);
			expect(a.errorMessage).toBe('Failed to cancel the job');
			expect(a.cancelling).toBe(false);
			expect(calls).toEqual([]);
		});
	});

	describe('remove', () => {
		it('does nothing without a job', async () => {
			const a = make();
			await a.remove(undefined);
			expect(deleteJobMock).not.toHaveBeenCalled();
			expectIdle(a);
		});

		it('closes the confirmation, deletes, then dismisses and refreshes', async () => {
			const d = deferred();
			deleteJobMock.mockReturnValue(d.promise);
			const a = make();
			a.confirmDelete = true;
			a.errorMessage = 'old';
			const p = a.remove(createJob({ id: 'j1' }));
			expect(a.confirmDelete).toBe(false);
			expect(a.deleting).toBe(true);
			expect(a.errorMessage).toBeNull();
			d.resolve();
			await p;
			expect(deleteJobMock).toHaveBeenCalledWith('j1');
			expect(calls).toEqual(['dismiss', 'refresh']);
			expect(a.deleting).toBe(false);
		});

		it('shows an Error failure message', async () => {
			deleteJobMock.mockRejectedValue(new Error('nope'));
			const a = make();
			await a.remove(createJob());
			expect(a.errorMessage).toBe('nope');
			expect(a.deleting).toBe(false);
			expect(calls).toEqual([]);
		});

		it('shows the fallback for a non-Error failure', async () => {
			deleteJobMock.mockRejectedValue('x');
			const a = make();
			await a.remove(createJob());
			expect(a.errorMessage).toBe('Failed to delete the job');
			expect(a.deleting).toBe(false);
			expect(calls).toEqual([]);
		});
	});

	describe('startRip', () => {
		it('does nothing without a job', async () => {
			const a = make();
			await a.startRip(undefined, createJob(), () => true);
			expect(resolveJobMock).not.toHaveBeenCalled();
			expectIdle(a);
		});

		it('resolves the job, then dismisses and refreshes, with the flag up while pending', async () => {
			const d = deferred();
			resolveJobMock.mockReturnValue(d.promise);
			const a = make();
			a.errorMessage = 'old';
			const p = a.startRip(
				createJob({ id: 'j1', title: 'Movie', year: 2020, disc_number: 1, disc_total: 2 }),
				undefined,
				() => false
			);
			expect(a.starting).toBe(true);
			expect(a.errorMessage).toBeNull();
			d.resolve();
			await p;
			expect(resolveJobMock).toHaveBeenCalledWith('j1', {
				title: 'Movie',
				year: 2020,
				disc_number: 1,
				disc_total: 2
			});
			expect(calls).toEqual(['dismiss', 'refresh']);
			expect(a.starting).toBe(false);
		});

		it("uses detailJob's identity over job's", async () => {
			resolveJobMock.mockResolvedValue(undefined);
			await make().startRip(
				createJob({ id: 'j1', title: 'Old', year: 1999 }),
				createJob({ id: 'j1', title: 'Fresh', year: 2021, disc_number: 3, disc_total: 4 }),
				() => false
			);
			expect(resolveJobMock).toHaveBeenCalledWith('j1', {
				title: 'Fresh',
				year: 2021,
				disc_number: 3,
				disc_total: 4
			});
		});

		it.each([['   '], [''], [null]])('refuses a blank title (%j) without a request', async (title) => {
			const a = make();
			await a.startRip(createJob({ title }), undefined, () => true);
			expect(a.errorMessage).toBe('A title is required to start. Open Info or Search to set one.');
			expect(a.starting).toBe(false);
			expect(resolveJobMock).not.toHaveBeenCalled();
			expect(calls).toEqual([]);
		});

		it('trims the title and sends null year, disc_number and disc_total', async () => {
			resolveJobMock.mockResolvedValue(undefined);
			await make().startRip(
				createJob({ id: 'j1', title: '  Movie  ', year: null, disc_number: null, disc_total: null }),
				undefined,
				() => false
			);
			expect(resolveJobMock).toHaveBeenCalledWith('j1', {
				title: 'Movie',
				year: null,
				disc_number: null,
				disc_total: null
			});
		});

		it('starts the waiting job too when the review gate is on', async () => {
			resolveJobMock.mockResolvedValue(undefined);
			startWaitingJobMock.mockResolvedValue(undefined);
			await make().startRip(createJob({ id: 'j1' }), undefined, () => true);
			expect(startWaitingJobMock).toHaveBeenCalledWith('j1');
		});

		it('reads the review gate after the resolve lands, so a countdown start in between skips startWaitingJob', async () => {
			let gate = true;
			resolveJobMock.mockImplementation(async () => {
				gate = false;
			});
			await make().startRip(createJob({ id: 'j1' }), undefined, () => gate);
			expect(startWaitingJobMock).not.toHaveBeenCalled();
			expect(calls).toEqual(['dismiss', 'refresh']);
		});

		it('does not start the waiting job when the review gate is off', async () => {
			resolveJobMock.mockResolvedValue(undefined);
			await make().startRip(createJob({ id: 'j1' }), undefined, () => false);
			expect(startWaitingJobMock).not.toHaveBeenCalled();
		});

		it('shows an Error failure message', async () => {
			resolveJobMock.mockRejectedValue(new Error('nope'));
			const a = make();
			await a.startRip(createJob(), undefined, () => false);
			expect(a.errorMessage).toBe('nope');
			expect(a.starting).toBe(false);
			expect(calls).toEqual([]);
		});

		it('shows the fallback for a non-Error failure', async () => {
			resolveJobMock.mockRejectedValue('x');
			const a = make();
			await a.startRip(createJob(), undefined, () => false);
			expect(a.errorMessage).toBe('Failed to start the rip');
			expect(a.starting).toBe(false);
			expect(calls).toEqual([]);
		});
	});

	describe('setPaused', () => {
		it('does nothing without a job', async () => {
			const a = make();
			await a.setPaused(undefined, true);
			expect(pauseWaitingJobMock).not.toHaveBeenCalled();
			expectIdle(a);
		});

		it.each([true, false])('sends pause=%s, then refreshes only', async (paused) => {
			const d = deferred();
			pauseWaitingJobMock.mockReturnValue(d.promise);
			const a = make();
			a.errorMessage = 'old';
			const p = a.setPaused(createJob({ id: 'j1' }), paused);
			expect(a.pauseBusy).toBe(true);
			expect(a.errorMessage).toBeNull();
			d.resolve();
			await p;
			expect(pauseWaitingJobMock).toHaveBeenCalledWith('j1', paused);
			expect(calls).toEqual(['refresh']);
			expect(a.pauseBusy).toBe(false);
		});

		it('shows an Error failure message', async () => {
			pauseWaitingJobMock.mockRejectedValue(new Error('nope'));
			const a = make();
			await a.setPaused(createJob(), true);
			expect(a.errorMessage).toBe('nope');
			expect(a.pauseBusy).toBe(false);
			expect(calls).toEqual([]);
		});

		it('shows the fallback for a non-Error failure', async () => {
			pauseWaitingJobMock.mockRejectedValue('x');
			const a = make();
			await a.setPaused(createJob(), true);
			expect(a.errorMessage).toBe('Failed to update pause');
			expect(a.pauseBusy).toBe(false);
			expect(calls).toEqual([]);
		});
	});
});
