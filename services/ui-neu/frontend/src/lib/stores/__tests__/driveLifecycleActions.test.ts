import { describe, it, expect, vi, beforeEach } from 'vitest';

const enrollDriveMock = vi.fn();
const ignoreDriveMock = vi.fn();
const unignoreDriveMock = vi.fn();
vi.mock('$lib/api/drives', () => ({
	enrollDrive: (...a: unknown[]) => enrollDriveMock(...a),
	ignoreDrive: (...a: unknown[]) => ignoreDriveMock(...a),
	unignoreDrive: (...a: unknown[]) => unignoreDriveMock(...a)
}));

import { DriveLifecycleActions } from '$lib/stores/drive-lifecycle-actions.svelte';

const onchanged = vi.fn();

function make() {
	return new DriveLifecycleActions(onchanged);
}

function deferred() {
	let resolve!: () => void;
	const promise = new Promise<void>((r) => (resolve = r));
	return { promise, resolve };
}

beforeEach(() => {
	for (const m of [enrollDriveMock, ignoreDriveMock, unignoreDriveMock, onchanged]) {
		m.mockReset();
	}
});

describe.each([
	['enroll', enrollDriveMock, 'enroll'],
	['ignore', ignoreDriveMock, 'other'],
	['unignore', unignoreDriveMock, 'other']
] as const)('%s', (method, apiMock, kind) => {
	it('calls its API with the id and reloads once', async () => {
		const a = make();
		await a[method]('d1');
		expect(apiMock).toHaveBeenCalledWith('d1');
		expect(onchanged).toHaveBeenCalledTimes(1);
	});

	it('marks the drive busy while pending and clears it when done', async () => {
		const d = deferred();
		apiMock.mockReturnValue(d.promise);
		const a = make();
		const p = a[method]('d1');
		expect(a.busy).toEqual({ d1: kind });
		d.resolve();
		await p;
		expect(a.busy).toEqual({});
	});

	it('records an Error message, skips the reload and clears busy', async () => {
		apiMock.mockRejectedValue(new Error('boom'));
		const a = make();
		await a[method]('d1');
		expect(a.errors).toEqual({ d1: 'boom' });
		expect(onchanged).not.toHaveBeenCalled();
		expect(a.busy).toEqual({});
	});

	it('records a fixed message for a non-Error failure', async () => {
		apiMock.mockRejectedValue('nope');
		const a = make();
		await a[method]('d1');
		expect(a.errors).toEqual({ d1: 'Action failed' });
	});
});

describe('a new action', () => {
	it("clears that id's earlier error and leaves other ids alone", async () => {
		const d = deferred();
		enrollDriveMock.mockReturnValue(d.promise);
		const a = make();
		a.errors = { d1: 'old', d2: 'other' };
		a.busy = { d2: 'other' };
		const p = a.enroll('d1');
		expect(a.errors).toEqual({ d2: 'other' });
		expect(a.busy).toEqual({ d2: 'other', d1: 'enroll' });
		d.resolve();
		await p;
		expect(a.errors).toEqual({ d2: 'other' });
		expect(a.busy).toEqual({ d2: 'other' });
	});
});
