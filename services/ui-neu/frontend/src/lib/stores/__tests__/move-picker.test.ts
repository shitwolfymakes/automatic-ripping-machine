import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { DirectoryListing, FileEntry, FileRoot } from '$lib/api/files';

vi.mock('$lib/api/files', () => ({ fetchRoots: vi.fn(), fetchDirectory: vi.fn() }));

import { fetchDirectory } from '$lib/api/files';
import { FilesBrowser } from '../files-browser.svelte';
import { MovePicker } from '../move-picker.svelte';

const mockDir = vi.mocked(fetchDirectory);

const dir = (name: string) => ({ name, type: 'directory' }) as FileEntry;
const file = (name: string) => ({ name, type: 'file' }) as FileEntry;
const listingOf = (entries: FileEntry[], extra: Partial<DirectoryListing> = {}) =>
	({ entries, ...extra }) as DirectoryListing;

function setup(selected: string[] = ['raw::a']) {
	const browser = new FilesBrowser();
	browser.current = { root: 'raw', subpath: 'src' };
	browser.selectedKeys = new Set(selected);
	return { browser, picker: new MovePicker(browser) };
}

beforeEach(() => {
	mockDir.mockReset();
});

describe('MovePicker open', () => {
	it('does nothing when nothing is selected', async () => {
		const { picker } = setup([]);
		await picker.open();
		expect(picker.isOpen).toBe(false);
		expect(mockDir).not.toHaveBeenCalled();
	});

	it('opens on the browser position and loads that folder', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')]));
		await picker.open();
		expect(picker.isOpen).toBe(true);
		expect(picker.location).toEqual({ root: 'raw', subpath: 'src' });
		expect(mockDir).toHaveBeenCalledWith('raw', 'src');
		expect(picker.listing?.entries).toHaveLength(1);
	});

	it('sets the location and open flag before the load resolves', async () => {
		const { picker } = setup();
		let resolve!: (l: DirectoryListing) => void;
		mockDir.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		const pending = picker.open();
		expect(picker.isOpen).toBe(true);
		expect(picker.location).toEqual({ root: 'raw', subpath: 'src' });
		resolve(listingOf([]));
		await pending;
	});
});

describe('MovePicker load', () => {
	it('moves to the loaded folder and stores its listing', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')]));
		await picker.load('music', 'a/b');
		expect(picker.location).toEqual({ root: 'music', subpath: 'a/b' });
		expect(picker.listing?.entries[0].name).toBe('x');
	});

	it('keeps the old location and listing when the fetch fails', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')]));
		await picker.load('raw', 'src');
		mockDir.mockRejectedValueOnce(new Error('boom'));
		await picker.load('music', 'z');
		expect(picker.location).toEqual({ root: 'raw', subpath: 'src' });
		expect(picker.listing?.entries[0].name).toBe('x');
		expect(picker.loading).toBe(false);
	});

	it('is loading while the fetch is pending and not after', async () => {
		const { picker } = setup();
		let resolve!: (l: DirectoryListing) => void;
		mockDir.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		const pending = picker.load('raw', '');
		expect(picker.loading).toBe(true);
		resolve(listingOf([]));
		await pending;
		expect(picker.loading).toBe(false);
	});
});

describe('MovePicker folders', () => {
	it('is empty with no listing', () => {
		const { picker } = setup();
		expect(picker.folders).toEqual([]);
	});

	it('hides the selected folders when browsing the source directory', async () => {
		const { picker } = setup(['raw::src/a']);
		mockDir.mockResolvedValueOnce(listingOf([dir('a'), dir('b'), file('f')]));
		await picker.open();
		expect(picker.folders.map((f) => f.name)).toEqual(['b']);
	});

	it('shows every folder when browsing elsewhere', async () => {
		const { picker } = setup(['raw::src/a']);
		mockDir.mockResolvedValueOnce(listingOf([dir('a'), dir('b'), file('f')]));
		await picker.load('music', 'src');
		expect(picker.folders.map((f) => f.name)).toEqual(['a', 'b']);
	});
});

describe('MovePicker atSource', () => {
	it('is true at the browser location', () => {
		const { picker } = setup();
		picker.location = { root: 'raw', subpath: 'src' };
		expect(picker.atSource).toBe(true);
	});

	it('is false at another subpath of the same root', () => {
		const { picker } = setup();
		picker.location = { root: 'raw', subpath: 'src/deeper' };
		expect(picker.atSource).toBe(false);
	});

	it('is false at another root', () => {
		const { picker } = setup();
		picker.location = { root: 'music', subpath: 'src' };
		expect(picker.atSource).toBe(false);
	});
});

describe('MovePicker canGoUp', () => {
	it('is false at the top of the source root', () => {
		const { browser, picker } = setup();
		browser.current = { root: 'raw', subpath: '' };
		picker.location = { root: 'raw', subpath: '' };
		expect(picker.canGoUp).toBe(false);
	});

	it('is true below the root', () => {
		const { picker } = setup();
		picker.location = { root: 'raw', subpath: 'src/deeper' };
		expect(picker.canGoUp).toBe(true);
	});

	it('is true at the top of a different root', () => {
		const { picker } = setup();
		picker.location = { root: 'music', subpath: '' };
		expect(picker.canGoUp).toBe(true);
	});
});

describe('MovePicker goUp', () => {
	it('loads the parent folder in the same root', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([], { parent_subpath: 'p' }));
		await picker.load('raw', 'p/q');
		mockDir.mockResolvedValueOnce(listingOf([]));
		await picker.goUp();
		expect(mockDir).toHaveBeenLastCalledWith('raw', 'p');
		expect(picker.location).toEqual({ root: 'raw', subpath: 'p' });
	});

	it('does nothing when it cannot go up', async () => {
		const { browser, picker } = setup();
		browser.current = { root: 'raw', subpath: '' };
		picker.location = { root: 'raw', subpath: '' };
		await picker.goUp();
		expect(mockDir).not.toHaveBeenCalled();
	});

	it('does nothing when the listing has no parent', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([], { parent_subpath: null }));
		await picker.load('music', '');
		mockDir.mockClear();
		await picker.goUp();
		expect(mockDir).not.toHaveBeenCalled();
	});

	it('does nothing when there is no listing', async () => {
		const { picker } = setup();
		picker.location = { root: 'music', subpath: '' };
		await picker.goUp();
		expect(mockDir).not.toHaveBeenCalled();
	});
});

describe('MovePicker close', () => {
	it('closes the dialog and drops the listing', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')]));
		await picker.open();
		picker.close();
		expect(picker.isOpen).toBe(false);
		expect(picker.listing).toBeNull();
	});
});

describe('MovePicker displayPath', () => {
	it('shows the label of a known root', () => {
		const { browser, picker } = setup();
		browser.roots = [{ key: 'raw', label: 'Raw rips' } as FileRoot];
		picker.location = { root: 'raw', subpath: '' };
		expect(picker.displayPath()).toBe('Raw rips');
	});

	it('falls back to the key of an unknown root', () => {
		const { picker } = setup();
		picker.location = { root: 'mystery', subpath: '' };
		expect(picker.displayPath()).toBe('mystery');
	});

	it('appends the subpath to the label', () => {
		const { browser, picker } = setup();
		browser.roots = [{ key: 'raw', label: 'Raw rips' } as FileRoot];
		picker.location = { root: 'raw', subpath: 'a/b' };
		expect(picker.displayPath()).toBe('Raw rips/a/b');
	});
});
