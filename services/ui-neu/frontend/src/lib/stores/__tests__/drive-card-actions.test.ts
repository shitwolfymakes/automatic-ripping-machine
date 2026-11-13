import { describe, it, expect, vi, beforeEach } from 'vitest';

const unenrollDriveMock = vi.fn();
const updateDriveMock = vi.fn();
const triggerManualMock = vi.fn();
vi.mock('$lib/api/drives', () => ({
	unenrollDrive: (...a: unknown[]) => unenrollDriveMock(...a),
	updateDrive: (...a: unknown[]) => updateDriveMock(...a)
}));
vi.mock('$lib/api/jobs', () => ({
	triggerManual: (...a: unknown[]) => triggerManualMock(...a)
}));

import { DriveCardActions } from '$lib/stores/drive-card-actions.svelte';

const refresh = vi.fn();

function make() {
	return new DriveCardActions(refresh);
}

function deferred() {
	let resolve!: () => void;
	const promise = new Promise<void>((r) => (resolve = r));
	return { promise, resolve };
}

beforeEach(() => {
	for (const m of [unenrollDriveMock, updateDriveMock, triggerManualMock, refresh]) {
		m.mockReset();
	}
});

describe('startManualRip', () => {
	it('sends the picked session, clears it and refreshes', async () => {
		const a = make();
		a.selectedSessionId = 's1';
		await a.startManualRip('d1');
		expect(triggerManualMock).toHaveBeenCalledWith({ drive_id: 'd1', session_id: 's1' });
		expect(a.selectedSessionId).toBe('');
		expect(refresh).toHaveBeenCalledTimes(1);
	});

	it('sends a null session when none is picked', async () => {
		await make().startManualRip('d1');
		expect(triggerManualMock).toHaveBeenCalledWith({ drive_id: 'd1', session_id: null });
	});

	it('is busy while in flight and ignores a second call', async () => {
		const d = deferred();
		triggerManualMock.mockReturnValue(d.promise);
		const a = make();
		const first = a.startManualRip('d1');
		expect(a.triggering).toBe(true);
		await a.startManualRip('d1');
		expect(triggerManualMock).toHaveBeenCalledTimes(1);
		d.resolve();
		await first;
		expect(a.triggering).toBe(false);
	});

	it('clears an earlier error when it starts', async () => {
		const a = make();
		a.manualError = 'old';
		const d = deferred();
		triggerManualMock.mockReturnValue(d.promise);
		const p = a.startManualRip('d1');
		expect(a.manualError).toBeNull();
		d.resolve();
		await p;
	});

	it('shows the Error message and keeps the picked session on failure', async () => {
		triggerManualMock.mockRejectedValue(new Error('boom'));
		const a = make();
		a.selectedSessionId = 's1';
		await a.startManualRip('d1');
		expect(a.manualError).toBe('boom');
		expect(a.selectedSessionId).toBe('s1');
		expect(refresh).not.toHaveBeenCalled();
		expect(a.triggering).toBe(false);
	});

	it('falls back to a fixed message for a non-Error failure', async () => {
		triggerManualMock.mockRejectedValue('nope');
		const a = make();
		await a.startManualRip('d1');
		expect(a.manualError).toBe('Manual rip failed');
	});
});

describe('requestUnenroll and cancelUnenroll', () => {
	it('requestUnenroll opens the confirmation and clears an earlier error', () => {
		const a = make();
		a.unenrollError = 'old';
		a.requestUnenroll();
		expect(a.confirmUnenrollOpen).toBe(true);
		expect(a.unenrollError).toBeNull();
	});

	it('cancelUnenroll closes the confirmation', () => {
		const a = make();
		a.requestUnenroll();
		a.cancelUnenroll();
		expect(a.confirmUnenrollOpen).toBe(false);
	});
});

describe('confirmUnenroll', () => {
	it('closes the confirmation, sends the id and refreshes', async () => {
		const a = make();
		a.requestUnenroll();
		await a.confirmUnenroll('d1');
		expect(a.confirmUnenrollOpen).toBe(false);
		expect(unenrollDriveMock).toHaveBeenCalledWith('d1');
		expect(refresh).toHaveBeenCalledTimes(1);
		expect(a.unenrolling).toBe(false);
	});

	it('is busy while the request is in flight', async () => {
		const d = deferred();
		unenrollDriveMock.mockReturnValue(d.promise);
		const a = make();
		const p = a.confirmUnenroll('d1');
		expect(a.unenrolling).toBe(true);
		d.resolve();
		await p;
		expect(a.unenrolling).toBe(false);
	});

	it('waits for the refresh before it is idle', async () => {
		const d = deferred();
		refresh.mockReturnValue(d.promise);
		const a = make();
		const p = a.confirmUnenroll('d1');
		await Promise.resolve();
		await Promise.resolve();
		expect(a.unenrolling).toBe(true);
		d.resolve();
		await p;
		expect(a.unenrolling).toBe(false);
	});

	it('shows the Error message on failure', async () => {
		unenrollDriveMock.mockRejectedValue(new Error('boom'));
		const a = make();
		await a.confirmUnenroll('d1');
		expect(a.unenrollError).toBe('boom');
		expect(a.unenrolling).toBe(false);
	});

	it('falls back to a fixed message for a non-Error failure', async () => {
		unenrollDriveMock.mockRejectedValue('nope');
		const a = make();
		await a.confirmUnenroll('d1');
		expect(a.unenrollError).toBe('Unenroll failed');
	});
});

describe('toggleUhd', () => {
	it.each([
		[true, false],
		[false, true],
		[null, true]
	])('sends the flipped value for %s', async (current, sent) => {
		await make().toggleUhd({ id: 'd1', uhd_capable: current });
		expect(updateDriveMock).toHaveBeenCalledWith('d1', { uhd_capable: sent });
		expect(refresh).toHaveBeenCalledTimes(1);
	});

	it('is busy while in flight', async () => {
		const d = deferred();
		updateDriveMock.mockReturnValue(d.promise);
		const a = make();
		const p = a.toggleUhd({ id: 'd1', uhd_capable: false });
		expect(a.togglingUhd).toBe(true);
		d.resolve();
		await p;
		expect(a.togglingUhd).toBe(false);
	});

	it('ignores a failure', async () => {
		updateDriveMock.mockRejectedValue(new Error('boom'));
		const a = make();
		await expect(a.toggleUhd({ id: 'd1', uhd_capable: false })).resolves.toBeUndefined();
		expect(refresh).not.toHaveBeenCalled();
		expect(a.togglingUhd).toBe(false);
	});
});

describe('setMode', () => {
	it.each([
		['auto', 'auto'],
		['manual', 'manual'],
		['', null]
	])('sends %j as %j', async (next, sent) => {
		await make().setMode('d1', next);
		expect(updateDriveMock).toHaveBeenCalledWith('d1', { drive_mode: sent });
		expect(refresh).toHaveBeenCalledTimes(1);
	});

	it('is busy while in flight', async () => {
		const d = deferred();
		updateDriveMock.mockReturnValue(d.promise);
		const a = make();
		const p = a.setMode('d1', 'auto');
		expect(a.togglingMode).toBe(true);
		d.resolve();
		await p;
		expect(a.togglingMode).toBe(false);
	});

	it('ignores a failure', async () => {
		updateDriveMock.mockRejectedValue(new Error('boom'));
		const a = make();
		await expect(a.setMode('d1', 'auto')).resolves.toBeUndefined();
		expect(refresh).not.toHaveBeenCalled();
		expect(a.togglingMode).toBe(false);
	});
});
