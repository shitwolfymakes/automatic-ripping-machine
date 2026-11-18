import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchIsoLibraryMock = vi.fn();
const fetchIsoFoldersMock = vi.fn();
vi.mock('$lib/api/iso', () => ({
	fetchIsoLibrary: (...a: unknown[]) => fetchIsoLibraryMock(...a),
	fetchIsoFolders: (...a: unknown[]) => fetchIsoFoldersMock(...a)
}));

import { ApiError } from '$lib/api/client';
import { IsoLibraryBrowser } from '$lib/stores/iso-library-browser.svelte';
import type { IsoFolderListing, IsoLibraryListing } from '$lib/types/api.gen';

function library(subpath: string, hostPath = '/host/iso'): IsoLibraryListing {
	return { subpath, parent_subpath: null, host_path: hostPath, entries: [] } as unknown as IsoLibraryListing;
}

function folders(hostPath = '/host/iso'): IsoFolderListing {
	return { host_path: hostPath, entries: [] } as unknown as IsoFolderListing;
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
	fetchIsoLibraryMock.mockReset();
	fetchIsoFoldersMock.mockReset();
});

describe('IsoLibraryBrowser.loadLibrary', () => {
	it('sets subpath and loading and clears the failure states before the fetch resolves', async () => {
		const b = new IsoLibraryBrowser();
		b.notConfigured = true;
		b.loadError = new Error('old');
		const d = deferred<IsoLibraryListing>();
		fetchIsoLibraryMock.mockReturnValue(d.promise);

		const pending = b.loadLibrary('Movies');

		expect(b.subpath).toBe('Movies');
		expect(b.loading).toBe(true);
		expect(b.notConfigured).toBe(false);
		expect(b.loadError).toBeNull();
		expect(fetchIsoLibraryMock).toHaveBeenCalledWith('Movies');
		d.resolve(library('Movies'));
		await pending;
	});

	it('applies the listing and host path, resets activeIndex and resolves true', async () => {
		const b = new IsoLibraryBrowser();
		b.activeIndex = 4;
		const result = library('Movies', '/mnt/nas');
		fetchIsoLibraryMock.mockResolvedValue(result);

		expect(await b.loadLibrary('Movies')).toBe(true);

		expect(b.listing).toEqual(result);
		expect(b.hostPath).toBe('/mnt/nas');
		expect(b.activeIndex).toBe(0);
		expect(b.loading).toBe(false);
	});

	it('drops a response that resolves after a newer load started and resolves false', async () => {
		const b = new IsoLibraryBrowser();
		const slow = deferred<IsoLibraryListing>();
		const fast = library('B');
		fetchIsoLibraryMock.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(fast);

		const first = b.loadLibrary('A');
		expect(await b.loadLibrary('B')).toBe(true);
		slow.resolve(library('A'));

		expect(await first).toBe(false);
		expect(b.listing).toEqual(fast);
		expect(b.subpath).toBe('B');
	});

	it('sets notConfigured on a 503, clears both listings and resolves false', async () => {
		const b = new IsoLibraryBrowser();
		b.listing = library('x');
		b.folderListing = folders();
		fetchIsoLibraryMock.mockRejectedValue(new ApiError(503, 'unavailable', null));

		expect(await b.loadLibrary('')).toBe(false);

		expect(b.notConfigured).toBe(true);
		expect(b.loadError).toBeNull();
		expect(b.listing).toBeNull();
		expect(b.folderListing).toBeNull();
		expect(b.loading).toBe(false);
	});

	it('sets loadError to another Error', async () => {
		const b = new IsoLibraryBrowser();
		const err = new Error('boom');
		fetchIsoLibraryMock.mockRejectedValue(err);

		expect(await b.loadLibrary('')).toBe(false);

		expect(b.loadError).toBe(err);
		expect(b.notConfigured).toBe(false);
	});

	it('treats a non-503 ApiError as a load error', async () => {
		const b = new IsoLibraryBrowser();
		const err = new ApiError(500, 'server', null);
		fetchIsoLibraryMock.mockRejectedValue(err);

		await b.loadLibrary('');

		expect(b.loadError).toBe(err);
		expect(b.notConfigured).toBe(false);
	});

	it('sets a fallback loadError for a non-Error rejection', async () => {
		const b = new IsoLibraryBrowser();
		fetchIsoLibraryMock.mockRejectedValue('nope');

		await b.loadLibrary('');

		expect(b.loadError?.message).toBe('Could not load the library.');
	});

	it('changes nothing when a failure rejects after a newer load started', async () => {
		const b = new IsoLibraryBrowser();
		const slow = deferred<IsoLibraryListing>();
		const fast = library('B');
		fetchIsoLibraryMock.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(fast);

		const first = b.loadLibrary('A');
		await b.loadLibrary('B');
		slow.reject(new Error('late'));

		expect(await first).toBe(false);
		expect(b.listing).toEqual(fast);
		expect(b.loadError).toBeNull();
		expect(b.loading).toBe(false);
	});
});

describe('IsoLibraryBrowser.loadFolders', () => {
	it('sets loading and an empty subpath, then applies the folders', async () => {
		const b = new IsoLibraryBrowser();
		b.subpath = 'Movies';
		b.activeIndex = 3;
		const d = deferred<IsoFolderListing>();
		fetchIsoFoldersMock.mockReturnValue(d.promise);

		const pending = b.loadFolders();
		expect(b.subpath).toBe('');
		expect(b.loading).toBe(true);

		const result = folders('/mnt/discs');
		d.resolve(result);
		await pending;

		expect(b.folderListing).toEqual(result);
		expect(b.hostPath).toBe('/mnt/discs');
		expect(b.activeIndex).toBe(0);
		expect(b.loading).toBe(false);
	});

	it('drops a response that resolves after a newer load started', async () => {
		const b = new IsoLibraryBrowser();
		const slow = deferred<IsoFolderListing>();
		const fast = folders('/fast');
		fetchIsoFoldersMock.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(fast);

		const first = b.loadFolders();
		await b.loadFolders();
		slow.resolve(folders('/slow'));
		await first;

		expect(b.folderListing).toEqual(fast);
		expect(b.hostPath).toBe('/fast');
	});

	it('sets notConfigured on a 503 and clears both listings', async () => {
		const b = new IsoLibraryBrowser();
		b.listing = library('x');
		fetchIsoFoldersMock.mockRejectedValue(new ApiError(503, 'unavailable', null));

		await b.loadFolders();

		expect(b.notConfigured).toBe(true);
		expect(b.listing).toBeNull();
		expect(b.folderListing).toBeNull();
		expect(b.loading).toBe(false);
	});

	it('sets loadError to another Error', async () => {
		const b = new IsoLibraryBrowser();
		const err = new Error('boom');
		fetchIsoFoldersMock.mockRejectedValue(err);

		await b.loadFolders();

		expect(b.loadError).toBe(err);
	});

	it('changes nothing when a failure rejects after a newer load started', async () => {
		const b = new IsoLibraryBrowser();
		const slow = deferred<IsoFolderListing>();
		const fast = folders('/fast');
		fetchIsoFoldersMock.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(fast);

		const first = b.loadFolders();
		await b.loadFolders();
		slow.reject(new Error('late'));
		await first;

		expect(b.folderListing).toEqual(fast);
		expect(b.loadError).toBeNull();
	});
});

describe('IsoLibraryBrowser.entryPath', () => {
	it('gives the bare name when nothing is listed', () => {
		expect(new IsoLibraryBrowser().entryPath('disc.iso')).toBe('disc.iso');
	});

	it('gives the bare name under a listing at the root', () => {
		const b = new IsoLibraryBrowser();
		b.listing = library('');
		expect(b.entryPath('disc.iso')).toBe('disc.iso');
	});

	it('prefixes the listing subpath', () => {
		const b = new IsoLibraryBrowser();
		b.listing = library('Movies');
		expect(b.entryPath('disc.iso')).toBe('Movies/disc.iso');
	});
});

describe('IsoLibraryBrowser.reset', () => {
	it('resets every field it names and leaves loading as it was', () => {
		const b = new IsoLibraryBrowser();
		b.subpath = 'Movies';
		b.listing = library('Movies');
		b.folderListing = folders();
		b.hostPath = '/mnt/nas';
		b.notConfigured = true;
		b.loadError = new Error('x');
		b.activeIndex = 5;
		b.loading = true;

		b.reset();

		expect(b.subpath).toBe('');
		expect(b.listing).toBeNull();
		expect(b.folderListing).toBeNull();
		expect(b.hostPath).toBe('');
		expect(b.notConfigured).toBe(false);
		expect(b.loadError).toBeNull();
		expect(b.activeIndex).toBe(0);
		expect(b.loading).toBe(true);
	});
});
