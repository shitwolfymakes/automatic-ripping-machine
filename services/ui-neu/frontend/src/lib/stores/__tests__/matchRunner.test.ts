import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { MatchPreview, MatchRequest } from '$lib/types/api.gen';
import { MatchRunner } from '../match-runner.svelte';

const matchIdentity = vi.fn();
vi.mock('$lib/api/identity', () => ({
	matchIdentity: (...a: unknown[]) => matchIdentity(...a)
}));

const PREVIEW = { tracks: [], outcomes: [{ source: 'tmdb', status: 'ok' }] } as unknown as MatchPreview;
const FAILED = (detail?: string) =>
	({ tracks: [], outcomes: [{ source: 'tmdb', status: 'error', detail }] }) as unknown as MatchPreview;
const PREVIEW_REQ = { source: 'tmdb', apply: false } as unknown as MatchRequest;
const APPLY_REQ = { source: 'tmdb', apply: true } as unknown as MatchRequest;

function setup(opts: { label?: string | null } = {}) {
	const state = { jobId: 'job-1', label: opts.label === undefined ? 'TMDb' : opts.label };
	const calls: string[] = [];
	const host = {
		jobId: vi.fn(() => state.jobId),
		placementLabel: vi.fn(() => state.label),
		closeForm: vi.fn(() => void calls.push('close')),
		reload: vi.fn(async () => void calls.push('reload'))
	};
	return { state, calls, host, runner: new MatchRunner(host) };
}

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	matchIdentity.mockReset();
});

describe('MatchRunner.run: a preview', () => {
	it('is busy while pending, then keeps the preview, its source and the request', async () => {
		const d = deferred<MatchPreview>();
		matchIdentity.mockReturnValue(d.promise);
		const { runner, host } = setup();
		const p = runner.run(PREVIEW_REQ);
		expect(runner.busy).toBe(true);
		expect(runner.lastRequest).toBe(PREVIEW_REQ);
		d.resolve(PREVIEW);
		await p;
		expect(matchIdentity).toHaveBeenCalledWith('job-1', PREVIEW_REQ);
		expect(runner.busy).toBe(false);
		expect(runner.preview).toEqual(PREVIEW);
		expect(runner.previewSource).toBe('tmdb');
		expect(runner.error).toBeNull();
		expect(host.closeForm).not.toHaveBeenCalled();
		expect(host.reload).not.toHaveBeenCalled();
	});

	it('keeps a null source when the request names none', async () => {
		matchIdentity.mockResolvedValue(PREVIEW);
		const { runner } = setup();
		await runner.run({ apply: false } as unknown as MatchRequest);
		expect(runner.previewSource).toBeNull();
	});

	it('names the label and the detail when an outcome failed, without reloading', async () => {
		matchIdentity.mockResolvedValue(FAILED('rate limited'));
		const { runner, host } = setup();
		await runner.run(PREVIEW_REQ);
		expect(runner.error).toBe(
			"TMDb didn't answer (rate limited). Nothing changed; the placement below is still TMDb's."
		);
		expect(runner.preview).toBeNull();
		expect(runner.busy).toBe(false);
		expect(host.reload).not.toHaveBeenCalled();
	});

	it('says "error" when a failed outcome has no detail', async () => {
		matchIdentity.mockResolvedValue(FAILED());
		const { runner } = setup();
		await runner.run(PREVIEW_REQ);
		expect(runner.error).toContain('(error)');
	});
});

describe('MatchRunner.applyPreview', () => {
	it('applies the request behind the preview with apply: true', async () => {
		matchIdentity.mockResolvedValueOnce(PREVIEW).mockResolvedValueOnce(PREVIEW);
		const { runner } = setup();
		await runner.run(PREVIEW_REQ);
		await runner.applyPreview();
		expect(matchIdentity).toHaveBeenLastCalledWith('job-1', { ...PREVIEW_REQ, apply: true });
	});

	it('sends nothing without a preview', () => {
		const { runner } = setup();
		expect(runner.applyPreview()).toBeUndefined();
		expect(matchIdentity).not.toHaveBeenCalled();
	});
});

describe('MatchRunner.run: an apply', () => {
	it('drops the preview, closes the form, then reloads', async () => {
		matchIdentity.mockResolvedValueOnce(PREVIEW).mockResolvedValueOnce(PREVIEW);
		const { runner, calls, host } = setup();
		await runner.run(PREVIEW_REQ);
		expect(runner.preview).toEqual(PREVIEW);
		let previewAtClose: unknown = 'unset';
		host.closeForm.mockImplementation(() => {
			previewAtClose = runner.preview;
			calls.push('close');
		});
		await runner.run(APPLY_REQ);
		expect(previewAtClose).toBeNull();
		expect(runner.preview).toBeNull();
		expect(runner.previewSource).toBeNull();
		expect(calls).toEqual(['close', 'reload']);
		expect(runner.busy).toBe(false);
	});

	it('reloads first when an outcome failed, then reports it', async () => {
		matchIdentity.mockResolvedValue(FAILED('boom'));
		const { runner, calls, host } = setup();
		await runner.run(APPLY_REQ);
		expect(calls).toEqual(['reload']);
		expect(host.closeForm).not.toHaveBeenCalled();
		expect(runner.error).toContain('(boom)');
		expect(runner.busy).toBe(false);
	});

	it('leaves no error when the job changed during the failed-outcome reload', async () => {
		matchIdentity.mockResolvedValue(FAILED('boom'));
		const { runner, state, host } = setup();
		host.reload.mockImplementation(async () => {
			state.jobId = 'job-2';
		});
		await runner.run(APPLY_REQ);
		expect(runner.error).toBeNull();
		expect(runner.preview).toBeNull();
		expect(runner.busy).toBe(false);
	});
});

describe('MatchRunner.run: a rejection', () => {
	it("reports an Error's message and the placement label's sentence", async () => {
		matchIdentity.mockRejectedValue(new Error('offline'));
		const { runner } = setup();
		await runner.run(PREVIEW_REQ);
		expect(runner.error).toBe("TMDb didn't answer (offline). Nothing changed; the placement below is still TMDb's.");
		expect(runner.busy).toBe(false);
	});

	it('says "error" for anything else, and "unchanged" with no placement label', async () => {
		matchIdentity.mockRejectedValue('nope');
		const { runner } = setup({ label: null });
		await runner.run(PREVIEW_REQ);
		expect(runner.error).toBe("TMDb didn't answer (error). Nothing changed; the placement below is unchanged.");
	});
});

describe('MatchRunner: stale runs', () => {
	it('drops a preview made stale by drop while pending', async () => {
		const d = deferred<MatchPreview>();
		matchIdentity.mockReturnValue(d.promise);
		const { runner } = setup();
		const p = runner.run(PREVIEW_REQ);
		runner.drop();
		d.resolve(PREVIEW);
		await p;
		expect(runner.preview).toBeNull();
		expect(runner.error).toBeNull();
		expect(runner.busy).toBe(false);
	});

	it('drops a failed preview made stale by drop while pending', async () => {
		const d = deferred<MatchPreview>();
		matchIdentity.mockReturnValue(d.promise);
		const { runner } = setup();
		const p = runner.run(PREVIEW_REQ);
		runner.drop();
		d.reject(new Error('late'));
		await p;
		expect(runner.error).toBeNull();
	});

	it('drops a run whose job changed before its response', async () => {
		const d = deferred<MatchPreview>();
		matchIdentity.mockReturnValue(d.promise);
		const { runner, state, host } = setup();
		const p = runner.run(APPLY_REQ);
		state.jobId = 'job-2';
		d.resolve(PREVIEW);
		await p;
		expect(runner.preview).toBeNull();
		expect(runner.error).toBeNull();
		expect(host.closeForm).not.toHaveBeenCalled();
		expect(host.reload).not.toHaveBeenCalled();
		expect(runner.busy).toBe(false);
	});

	it('keeps an apply that a drop overtook, since only previews go stale that way', async () => {
		const d = deferred<MatchPreview>();
		matchIdentity.mockReturnValue(d.promise);
		const { runner, host } = setup();
		const p = runner.run(APPLY_REQ);
		runner.drop();
		d.resolve(PREVIEW);
		await p;
		expect(host.reload).toHaveBeenCalledOnce();
	});
});

describe('MatchRunner.drop and reset', () => {
	it('drop clears the preview, its source and the error, and keeps lastRequest', async () => {
		matchIdentity.mockResolvedValue(PREVIEW);
		const { runner } = setup();
		await runner.run(PREVIEW_REQ);
		runner.error = 'x';
		runner.drop();
		expect(runner.preview).toBeNull();
		expect(runner.previewSource).toBeNull();
		expect(runner.error).toBeNull();
		expect(runner.lastRequest).toBe(PREVIEW_REQ);
		expect(runner.applyPreview()).toBeUndefined();
	});

	it('reset also forgets lastRequest', async () => {
		matchIdentity.mockResolvedValue(PREVIEW);
		const { runner } = setup();
		await runner.run(PREVIEW_REQ);
		runner.reset();
		expect(runner.preview).toBeNull();
		expect(runner.lastRequest).toBeNull();
	});
});
