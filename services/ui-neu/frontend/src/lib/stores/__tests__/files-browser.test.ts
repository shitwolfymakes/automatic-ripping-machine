import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { DirectoryListing, FileEntry, FileRoot } from '$lib/api/files';

vi.mock('$lib/api/files', () => ({ fetchRoots: vi.fn(), fetchDirectory: vi.fn() }));

import { fetchRoots, fetchDirectory } from '$lib/api/files';
import { FilesBrowser } from '../files-browser.svelte';

const mockRoots = vi.mocked(fetchRoots);
const mockDir = vi.mocked(fetchDirectory);

const root = (key: string) => ({ key, label: key }) as FileRoot;
const entry = (name: string, extra: Partial<FileEntry> = {}) => ({ name, type: 'file', ...extra }) as FileEntry;
const listingOf = (entries: FileEntry[], extra: Partial<DirectoryListing> = {}) =>
	({ entries, ...extra }) as DirectoryListing;

async function browserWith(entries: FileEntry[], subpath = '') {
	const b = new FilesBrowser();
	mockDir.mockResolvedValueOnce(listingOf(entries));
	await b.navigate('raw', subpath);
	return b;
}

const names = (b: FilesBrowser) => b.sortedEntries.map((e) => e.name);

beforeEach(() => {
	mockRoots.mockReset();
	mockDir.mockReset();
});

describe('FilesBrowser loadRoots', () => {
	it('orders the roots raw, transcode, completed, music and unknown ones last', async () => {
		mockRoots.mockResolvedValueOnce([root('other'), root('music'), root('completed'), root('transcode'), root('raw')]);
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.roots.map((r) => r.key)).toEqual(['raw', 'transcode', 'completed', 'music', 'other']);
	});

	it('picks the first root in order when none is current', async () => {
		mockRoots.mockResolvedValueOnce([root('music'), root('raw')]);
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.current).toEqual({ root: 'raw', subpath: '' });
	});

	it('keeps the current root when one is already set', async () => {
		mockRoots.mockResolvedValueOnce([root('raw')]);
		const b = new FilesBrowser();
		b.current = { root: 'music', subpath: 'a' };
		await b.loadRoots();
		expect(b.current).toEqual({ root: 'music', subpath: 'a' });
	});

	it('leaves the current position alone when there are no roots', async () => {
		mockRoots.mockResolvedValueOnce([]);
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.current).toEqual({ root: '', subpath: '' });
	});

	it('sorts a root without a key after the known ones', async () => {
		mockRoots.mockResolvedValueOnce([{ label: 'x' } as unknown as FileRoot, root('raw')]);
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.roots.map((r) => r.key)).toEqual(['raw', undefined]);
	});

	it('reports the message of an Error when the roots load fails', async () => {
		mockRoots.mockRejectedValueOnce(new Error('boom'));
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.error).toBe('boom');
		expect(b.filesError?.message).toBe('boom');
	});

	it('reports a fallback message when the roots load fails with a non-Error', async () => {
		mockRoots.mockRejectedValueOnce('nope');
		const b = new FilesBrowser();
		await b.loadRoots();
		expect(b.error).toBe('Failed to load roots');
	});
});

describe('FilesBrowser navigate', () => {
	it('starts loading with no error, listing or readonly flag', () => {
		const b = new FilesBrowser();
		expect(b.loading).toBe(true);
		expect(b.error).toBeNull();
		expect(b.filesError).toBeNull();
		expect(b.listing).toBeNull();
		expect(b.isReadonly).toBe(false);
	});

	it('loads the directory, moves current and clears the selection', async () => {
		const b = await browserWith([entry('a')]);
		b.toggleSelect('a');
		expect(b.selectedKeys.size).toBe(1);
		mockDir.mockResolvedValueOnce(listingOf([entry('b')], { readonly: true }));
		await b.navigate('raw', 'sub');
		expect(mockDir).toHaveBeenLastCalledWith('raw', 'sub');
		expect(b.current).toEqual({ root: 'raw', subpath: 'sub' });
		expect(b.selectedKeys.size).toBe(0);
		expect(names(b)).toEqual(['b']);
		expect(b.isReadonly).toBe(true);
		expect(b.loading).toBe(false);
		expect(b.error).toBeNull();
	});

	it('drops the listing and reports the message of an Error on failure', async () => {
		const b = await browserWith([entry('a')]);
		mockDir.mockRejectedValueOnce(new Error('denied'));
		await b.navigate('raw', 'x');
		expect(b.error).toBe('denied');
		expect(b.listing).toBeNull();
		expect(b.loading).toBe(false);
		expect(b.current).toEqual({ root: 'raw', subpath: 'x' });
	});

	it('reports a fallback message on a non-Error failure', async () => {
		const b = new FilesBrowser();
		mockDir.mockRejectedValueOnce('nope');
		await b.navigate('raw', '');
		expect(b.error).toBe('Failed to load directory');
	});

	it('clears an earlier error when navigating again', async () => {
		const b = new FilesBrowser();
		mockDir.mockRejectedValueOnce(new Error('x'));
		await b.navigate('raw', '');
		mockDir.mockResolvedValueOnce(listingOf([]));
		await b.navigate('raw', '');
		expect(b.error).toBeNull();
	});
});

describe('FilesBrowser sorting', () => {
	const mixed = () => [
		entry('b.txt', { size: 5, modified: '2024-01-02' }),
		entry('A.txt', { size: 9, modified: '2024-01-01' }),
		entry('zdir', { type: 'directory', size: 1, modified: '2024-01-03' }),
		entry('adir', { type: 'directory', size: 2, modified: '2024-01-04' })
	];

	it('has no entries without a listing', () => {
		expect(new FilesBrowser().sortedEntries).toEqual([]);
	});

	it('sorts by name ascending, ignoring case, with directories first', async () => {
		const b = await browserWith(mixed());
		expect(names(b)).toEqual(['adir', 'zdir', 'A.txt', 'b.txt']);
	});

	it('sorts by name descending with directories still first', async () => {
		const b = await browserWith(mixed());
		b.toggleSort('name');
		expect(names(b)).toEqual(['zdir', 'adir', 'b.txt', 'A.txt']);
	});

	it('sorts by size ascending and descending with directories first', async () => {
		const b = await browserWith(mixed());
		b.toggleSort('size');
		expect(names(b)).toEqual(['zdir', 'adir', 'b.txt', 'A.txt']);
		b.toggleSort('size');
		expect(names(b)).toEqual(['adir', 'zdir', 'A.txt', 'b.txt']);
	});

	it('sorts by modified newest first, then oldest first, with directories first', async () => {
		const b = await browserWith(mixed());
		b.toggleSort('modified');
		expect(b.sortDir).toBe('desc');
		expect(names(b)).toEqual(['adir', 'zdir', 'b.txt', 'A.txt']);
		b.toggleSort('modified');
		expect(names(b)).toEqual(['zdir', 'adir', 'A.txt', 'b.txt']);
	});

	it('treats a missing size and modified date as zero and empty', async () => {
		const b = await browserWith([entry('has', { size: 3, modified: '2024' }), entry('none')]);
		b.toggleSort('size');
		expect(names(b)).toEqual(['none', 'has']);
		b.toggleSort('modified');
		expect(names(b)).toEqual(['has', 'none']);
	});

	it('flips the direction on the same column and resets it on a new one', () => {
		const b = new FilesBrowser();
		b.toggleSort('name');
		expect(b.sortDir).toBe('desc');
		b.toggleSort('name');
		expect(b.sortDir).toBe('asc');
		b.toggleSort('size');
		expect([b.sortKey, b.sortDir]).toEqual(['size', 'asc']);
		b.toggleSort('modified');
		expect([b.sortKey, b.sortDir]).toEqual(['modified', 'desc']);
	});

	it('reports the direction only for the sorted column', () => {
		const b = new FilesBrowser();
		expect(b.sortIconDir('name')).toBe('asc');
		expect(b.sortIconDir('size')).toBeNull();
		b.toggleSort('name');
		expect(b.sortIconDir('name')).toBe('desc');
	});
});

describe('FilesBrowser selection', () => {
	it('builds item subpaths and selection keys at the top and below it', async () => {
		const b = new FilesBrowser();
		b.current = { root: 'raw', subpath: '' };
		expect(b.itemSubpath('a')).toBe('a');
		expect(b.selectionKey('a')).toBe('raw::a');
		b.current = { root: 'raw', subpath: 'x/y' };
		expect(b.itemSubpath('a')).toBe('x/y/a');
		expect(b.selectionKey('a')).toBe('raw::x/y/a');
	});

	it('toggles an entry on and off', async () => {
		const b = await browserWith([entry('a')]);
		b.toggleSelect('a');
		expect([...b.selectedKeys]).toEqual(['raw::a']);
		b.toggleSelect('a');
		expect(b.selectedKeys.size).toBe(0);
	});

	it('does nothing on select-all without a listing', () => {
		const b = new FilesBrowser();
		b.toggleSelectAll();
		expect(b.selectedKeys.size).toBe(0);
		expect(b.allSelected).toBe(false);
	});

	it('does not report all selected for an empty listing', async () => {
		const b = await browserWith([]);
		b.toggleSelectAll();
		expect(b.allSelected).toBe(false);
	});

	it('selects every entry, then clears them all', async () => {
		const b = await browserWith([entry('a'), entry('b')], 'sub');
		b.toggleSelect('a');
		expect(b.allSelected).toBe(false);
		b.toggleSelectAll();
		expect([...b.selectedKeys].sort()).toEqual(['raw::sub/a', 'raw::sub/b']);
		expect(b.allSelected).toBe(true);
		b.toggleSelectAll();
		expect(b.selectedKeys.size).toBe(0);
	});
});
