import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchIdentityMock = vi.fn();
const fetchNamingPreviewMock = vi.fn();
vi.mock('$lib/api/identity', () => ({
	fetchIdentity: (...a: unknown[]) => fetchIdentityMock(...a)
}));
vi.mock('$lib/api/jobs', () => ({
	fetchNamingPreview: (...a: unknown[]) => fetchNamingPreviewMock(...a)
}));

import { EpisodeIdentity } from '$lib/stores/episode-identity.svelte';

const IDENTITY = { tracks: [] };
const PREVIEW = {
	items: [
		{ track_id: 't1', output_name: 'A.mkv', output_path: '/out/A.mkv' },
		{ track_id: 't2', output_name: 'B.mkv', output_path: '/out/B.mkv' }
	]
};

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
	fetchIdentityMock.mockReset();
	fetchNamingPreviewMock.mockReset();
});

describe('EpisodeIdentity', () => {
	it('starts empty', () => {
		const state = new EpisodeIdentity(() => 'j1');
		expect(state.identity).toBeNull();
		expect(state.loadError).toBeNull();
		expect(state.loaded).toBe(false);
		expect(state.fileNames.size).toBe(0);
	});

	it('loads the identity, clears an earlier error, then fills the file names', async () => {
		fetchIdentityMock.mockResolvedValue(IDENTITY);
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const state = new EpisodeIdentity(() => 'j1');
		state.loadError = 'old';
		await state.load('j1');
		expect(fetchIdentityMock).toHaveBeenCalledWith('j1');
		expect(fetchNamingPreviewMock).toHaveBeenCalledWith('j1');
		expect(state.identity).toEqual(IDENTITY);
		expect(state.loadError).toBeNull();
		expect(state.loaded).toBe(true);
		expect(state.fileNames.get('t2')).toEqual({ name: 'B.mkv', path: '/out/B.mkv' });
		expect(state.fileNames.size).toBe(2);
	});

	it('gives no file names for a preview with no items', async () => {
		fetchIdentityMock.mockResolvedValue(IDENTITY);
		fetchNamingPreviewMock.mockResolvedValue({});
		const state = new EpisodeIdentity(() => 'j1');
		await state.load('j1');
		expect(state.fileNames.size).toBe(0);
	});

	it("keeps an Error's message when the identity fails, and still fetches file names", async () => {
		fetchIdentityMock.mockRejectedValue(new Error('boom'));
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const state = new EpisodeIdentity(() => 'j1');
		await state.load('j1');
		expect(state.loadError).toBe('boom');
		expect(state.identity).toBeNull();
		expect(state.loaded).toBe(true);
		expect(state.fileNames.size).toBe(2);
	});

	it('uses a generic message when the identity fails with a non-Error', async () => {
		fetchIdentityMock.mockRejectedValue('nope');
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const state = new EpisodeIdentity(() => 'j1');
		await state.load('j1');
		expect(state.loadError).toBe('Could not load episodes');
		expect(state.loaded).toBe(true);
	});

	it('keeps the identity and the old file names when the file names fail', async () => {
		fetchIdentityMock.mockResolvedValue(IDENTITY);
		fetchNamingPreviewMock.mockResolvedValueOnce(PREVIEW).mockRejectedValueOnce(new Error('x'));
		const state = new EpisodeIdentity(() => 'j1');
		await state.load('j1');
		await expect(state.load('j1')).resolves.toBeUndefined();
		expect(state.identity).toEqual(IDENTITY);
		expect(state.fileNames.size).toBe(2);
	});

	it('drops an identity response that arrives after the job changed', async () => {
		const pending = deferred<unknown>();
		fetchIdentityMock.mockReturnValue(pending.promise);
		let current = 'j1';
		const state = new EpisodeIdentity(() => current);
		const run = state.load('j1');
		current = 'j2';
		pending.resolve(IDENTITY);
		await run;
		expect(state.identity).toBeNull();
		expect(state.loaded).toBe(false);
		expect(fetchNamingPreviewMock).not.toHaveBeenCalled();
	});

	it('drops an identity failure that arrives after the job changed', async () => {
		const pending = deferred<unknown>();
		fetchIdentityMock.mockReturnValue(pending.promise);
		let current = 'j1';
		const state = new EpisodeIdentity(() => current);
		const run = state.load('j1');
		current = 'j2';
		pending.reject(new Error('late'));
		await run;
		expect(state.loadError).toBeNull();
		expect(state.loaded).toBe(false);
	});

	it('drops a file-name response that arrives after the job changed', async () => {
		const pending = deferred<unknown>();
		fetchIdentityMock.mockResolvedValue(IDENTITY);
		fetchNamingPreviewMock.mockReturnValue(pending.promise);
		let current = 'j1';
		const state = new EpisodeIdentity(() => current);
		const run = state.load('j1');
		await vi.waitFor(() => expect(fetchNamingPreviewMock).toHaveBeenCalled());
		current = 'j2';
		pending.resolve(PREVIEW);
		await run;
		expect(state.identity).toEqual(IDENTITY);
		expect(state.fileNames.size).toBe(0);
	});

	it('reset empties all four', async () => {
		fetchIdentityMock.mockResolvedValue(IDENTITY);
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const state = new EpisodeIdentity(() => 'j1');
		await state.load('j1');
		state.loadError = 'e';
		state.reset();
		expect(state.identity).toBeNull();
		expect(state.loaded).toBe(false);
		expect(state.loadError).toBeNull();
		expect(state.fileNames.size).toBe(0);
	});
});
