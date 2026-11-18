import { describe, it, expect, vi, beforeEach } from 'vitest';

const resolveJobMock = vi.fn();
const patchJobMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	resolveJob: (...a: unknown[]) => resolveJobMock(...a),
	patchJob: (...a: unknown[]) => patchJobMock(...a)
}));

import { MusicReleaseApply, type ReleaseApplyPlan } from '$lib/stores/music-release-apply.svelte';

const RESOLVE_BODY = { title: 'Album' } as unknown as ReleaseApplyPlan['resolveBody'];
const PATCH_BODY = { poster_url: 'x' } as unknown as NonNullable<ReturnType<ReleaseApplyPlan['patchBody']>>;

function plan(over: Partial<ReleaseApplyPlan> = {}): ReleaseApplyPlan {
	return {
		jobId: 'job-1',
		totalMismatch: false,
		needsMapping: false,
		resolveBody: RESOLVE_BODY,
		patchBody: () => PATCH_BODY,
		...over
	};
}

function deferred<T>() {
	let resolve!: (v: T) => void;
	const promise = new Promise<T>((res) => {
		resolve = res;
	});
	return { promise, resolve };
}

beforeEach(() => {
	resolveJobMock.mockReset().mockResolvedValue({});
	patchJobMock.mockReset().mockResolvedValue({});
});

describe('MusicReleaseApply', () => {
	it('starts with every field false or null', () => {
		const r = new MusicReleaseApply();
		expect(r.applying).toBe(false);
		expect(r.feedback).toBeNull();
		expect(r.confirmMismatch).toBe(false);
		expect(r.mappingPreview).toBe(false);
	});

	it('opens the mismatch gate with no request, and acceptMismatch lets the next apply pass', async () => {
		const r = new MusicReleaseApply();
		const p = plan({ totalMismatch: true });
		await r.apply(p);
		expect(r.confirmMismatch).toBe(true);
		expect(resolveJobMock).not.toHaveBeenCalled();
		r.acceptMismatch();
		expect(r.confirmMismatch).toBe(false);
		await r.apply(p);
		expect(resolveJobMock).toHaveBeenCalledTimes(1);
		expect(r.confirmMismatch).toBe(false);
	});

	it('opens the mapping gate with no request, and acceptMapping lets the next apply pass', async () => {
		const r = new MusicReleaseApply();
		const p = plan({ needsMapping: true });
		await r.apply(p);
		expect(r.mappingPreview).toBe(true);
		expect(resolveJobMock).not.toHaveBeenCalled();
		r.acceptMapping();
		expect(r.mappingPreview).toBe(false);
		await r.apply(p);
		expect(resolveJobMock).toHaveBeenCalledTimes(1);
	});

	it('asks the mismatch gate first, then the mapping gate', async () => {
		const r = new MusicReleaseApply();
		const p = plan({ totalMismatch: true, needsMapping: true });
		await r.apply(p);
		expect(r.confirmMismatch).toBe(true);
		expect(r.mappingPreview).toBe(false);
		r.acceptMismatch();
		await r.apply(p);
		expect(r.mappingPreview).toBe(true);
		expect(resolveJobMock).not.toHaveBeenCalled();
	});

	it('reset closes both gates and forgets both confirmations', async () => {
		const r = new MusicReleaseApply();
		const p = plan({ totalMismatch: true, needsMapping: true });
		r.acceptMismatch();
		r.acceptMapping();
		r.confirmMismatch = true;
		r.mappingPreview = true;
		r.reset();
		expect(r.confirmMismatch).toBe(false);
		expect(r.mappingPreview).toBe(false);
		await r.apply(p);
		expect(r.confirmMismatch).toBe(true);
		r.acceptMismatch();
		await r.apply(p);
		expect(r.mappingPreview).toBe(true);
		expect(resolveJobMock).not.toHaveBeenCalled();
	});

	it('resolves, then patches once, then calls onapply on success', async () => {
		const r = new MusicReleaseApply();
		const pending = deferred<unknown>();
		resolveJobMock.mockReturnValue(pending.promise);
		const patchBody = vi.fn(() => PATCH_BODY);
		const onapply = vi.fn();
		const run = r.apply(plan({ patchBody }), onapply);
		expect(r.applying).toBe(true);
		expect(resolveJobMock).toHaveBeenCalledWith('job-1', RESOLVE_BODY);
		expect(patchBody).not.toHaveBeenCalled();
		pending.resolve({});
		await run;
		expect(r.applying).toBe(false);
		expect(r.feedback).toEqual({ type: 'success', message: 'Release applied' });
		expect(patchBody).toHaveBeenCalledTimes(1);
		expect(patchJobMock).toHaveBeenCalledWith('job-1', PATCH_BODY);
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it('sends no PATCH when patchBody returns null', async () => {
		const r = new MusicReleaseApply();
		const onapply = vi.fn();
		await r.apply(plan({ patchBody: () => null }), onapply);
		expect(patchJobMock).not.toHaveBeenCalled();
		expect(onapply).toHaveBeenCalled();
		expect(r.feedback?.message).toBe('Release applied');
	});

	it('reports a failed PATCH as a success and still calls onapply', async () => {
		const r = new MusicReleaseApply();
		patchJobMock.mockRejectedValue(new Error('nope'));
		const onapply = vi.fn();
		await r.apply(plan(), onapply);
		expect(r.feedback).toEqual({ type: 'success', message: 'Identified; cover/track titles not saved' });
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it('reports a failed resolve with the Error message and skips patchBody, PATCH and onapply', async () => {
		const r = new MusicReleaseApply();
		resolveJobMock.mockRejectedValue(new Error('boom'));
		const patchBody = vi.fn(() => PATCH_BODY);
		const onapply = vi.fn();
		await r.apply(plan({ patchBody }), onapply);
		expect(r.feedback).toEqual({ type: 'error', message: 'boom' });
		expect(patchBody).not.toHaveBeenCalled();
		expect(patchJobMock).not.toHaveBeenCalled();
		expect(onapply).not.toHaveBeenCalled();
		expect(r.applying).toBe(false);
	});

	it('reports a non-Error resolve failure as Apply failed', async () => {
		const r = new MusicReleaseApply();
		resolveJobMock.mockRejectedValue('bad');
		await r.apply(plan());
		expect(r.feedback).toEqual({ type: 'error', message: 'Apply failed' });
	});

	it('reports a throwing patchBody as the error and skips onapply', async () => {
		const r = new MusicReleaseApply();
		const onapply = vi.fn();
		await r.apply(
			plan({
				patchBody: () => {
					throw new Error('closed');
				}
			}),
			onapply
		);
		expect(r.feedback).toEqual({ type: 'error', message: 'closed' });
		expect(patchJobMock).not.toHaveBeenCalled();
		expect(onapply).not.toHaveBeenCalled();
	});

	it('does not throw when no onapply is passed', async () => {
		const r = new MusicReleaseApply();
		await expect(r.apply(plan())).resolves.toBeUndefined();
		expect(r.feedback?.type).toBe('success');
	});
});
