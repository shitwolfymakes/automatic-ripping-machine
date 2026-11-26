import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchNamingPreviewMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	fetchNamingPreview: (...a: unknown[]) => fetchNamingPreviewMock(...a)
}));

import { NamingPreview } from '$lib/stores/naming-preview.svelte';
import type { JobNamingPreviewResponse } from '$lib/types/api.gen';

function answer(): JobNamingPreviewResponse {
	return { items: [] } as unknown as JobNamingPreviewResponse;
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

const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
	fetchNamingPreviewMock.mockReset();
});

describe('NamingPreview.load', () => {
	it('clears preview and problem, leaves loading and does not fetch when there is no session', () => {
		const n = new NamingPreview();
		n.preview = answer();
		n.problem = 'old problem';
		n.loading = true;
		const cancel = n.load('job-1', '');
		expect(n.preview).toBeNull();
		expect(n.problem).toBeNull();
		expect(n.loading).toBe(true);
		expect(fetchNamingPreviewMock).not.toHaveBeenCalled();
		expect(cancel()).toBeUndefined();
	});

	it('sets loading and fetches with the job id and session id', () => {
		fetchNamingPreviewMock.mockReturnValue(new Promise(() => {}));
		const n = new NamingPreview();
		n.load('job-1', 'sess-1');
		expect(n.loading).toBe(true);
		expect(fetchNamingPreviewMock).toHaveBeenCalledWith('job-1', 'sess-1');
	});

	it('sets preview and clears loading on success', async () => {
		const p = answer();
		fetchNamingPreviewMock.mockResolvedValue(p);
		const n = new NamingPreview();
		n.load('job-1', 'sess-1');
		await flush();
		expect(n.preview).toEqual(p);
		expect(n.loading).toBe(false);
	});

	it('sets the explained problem and clears loading when the fetch fails with an Error', async () => {
		fetchNamingPreviewMock.mockRejectedValue(new Error('naming failed: token {year} has no value'));
		const n = new NamingPreview();
		n.load('job-1', 'sess-1');
		await flush();
		expect(n.problem).toBe(
			"This job has no year, so {year} in the output path cannot be filled. Add it in the job's details, or choose a session whose output path does not use it or marks it optional as {year?}."
		);
		expect(n.loading).toBe(false);
	});

	it('sets the fallback problem when the fetch fails with a non-Error', async () => {
		fetchNamingPreviewMock.mockRejectedValue('boom');
		const n = new NamingPreview();
		n.load('job-1', 'sess-1');
		await flush();
		expect(n.problem).toBe('Preview failed');
		expect(n.loading).toBe(false);
	});

	it('drops the answer and the end of loading when cancelled before the fetch resolves', async () => {
		const d = deferred<JobNamingPreviewResponse>();
		fetchNamingPreviewMock.mockReturnValue(d.promise);
		const n = new NamingPreview();
		const cancel = n.load('job-1', 'sess-1');
		cancel();
		d.resolve(answer());
		await flush();
		expect(n.preview).toBeNull();
		expect(n.loading).toBe(true);
	});

	it('drops the problem and the end of loading when cancelled before the fetch rejects', async () => {
		const d = deferred<JobNamingPreviewResponse>();
		fetchNamingPreviewMock.mockReturnValue(d.promise);
		const n = new NamingPreview();
		const cancel = n.load('job-1', 'sess-1');
		cancel();
		d.reject(new Error('nope'));
		await flush();
		expect(n.problem).toBeNull();
		expect(n.loading).toBe(true);
	});

	it("clears the first load's preview and problem before its own fetch resolves", async () => {
		fetchNamingPreviewMock.mockResolvedValueOnce(answer());
		const n = new NamingPreview();
		n.load('job-1', 'sess-1');
		await flush();
		expect(n.preview).not.toBeNull();
		n.problem = 'stale';
		const d = deferred<JobNamingPreviewResponse>();
		fetchNamingPreviewMock.mockReturnValueOnce(d.promise);
		n.load('job-1', 'sess-2');
		expect(n.preview).toBeNull();
		expect(n.problem).toBeNull();
		d.resolve(answer());
		await flush();
		expect(n.preview).not.toBeNull();
	});
});
