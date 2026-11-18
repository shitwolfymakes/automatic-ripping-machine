import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import FilesPage from '../+page.svelte';
import * as stores from '$app/stores';
import * as auth from '$lib/stores/auth';
import {
	fetchRoots,
	fetchDirectory,
	renameFile,
	moveFile,
	deleteFile,
	createDirectory,
	fixPermissions
} from '$lib/api/files';
import type { DirectoryListing, FileEntry, FileRoot } from '$lib/api/files';
import { fetchOrphanFolders, deleteFolder, bulkDeleteFolders, cleanupTranscoder } from '$lib/api/maintenance';
import type { OrphanFoldersResponse } from '$lib/api/maintenance';
import { features } from '$lib/features';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

// Mutable copy so a test can switch the maintenance UI the shipped flag hides.
vi.mock('$lib/features', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/features')>();
	return { ...actual, features: { ...actual.features } };
});

// A writable page store, so a test can change ?root= / ?subpath= after mount.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	const page = writable({ url: new URL('http://localhost/files') });
	return {
		page: { subscribe: page.subscribe },
		// Test-only helper — not part of the real module's public API.
		__setUrl: (u: string) => page.set({ url: new URL(u) })
	};
});

vi.mock('$lib/api/files', () => ({
	fetchRoots: vi.fn(),
	fetchDirectory: vi.fn(),
	renameFile: vi.fn(),
	moveFile: vi.fn(),
	deleteFile: vi.fn(),
	createDirectory: vi.fn(),
	fixPermissions: vi.fn()
}));

vi.mock('$lib/api/maintenance', () => ({
	fetchOrphanFolders: vi.fn(),
	deleteFolder: vi.fn(),
	bulkDeleteFolders: vi.fn(),
	cleanupTranscoder: vi.fn()
}));

const setUrl = (stores as unknown as { __setUrl: (u: string) => void }).__setUrl;
const setRole = (auth as unknown as { __setRole: (r: string | null) => void }).__setRole;

const mockFetchRoots = vi.mocked(fetchRoots);
const mockFetchDirectory = vi.mocked(fetchDirectory);
const mockRename = vi.mocked(renameFile);
const mockMove = vi.mocked(moveFile);
const mockDelete = vi.mocked(deleteFile);
const mockCreateDirectory = vi.mocked(createDirectory);
const mockFixPermissions = vi.mocked(fixPermissions);
const mockFetchOrphans = vi.mocked(fetchOrphanFolders);
const mockDeleteOrphan = vi.mocked(deleteFolder);
const mockBulkDeleteOrphans = vi.mocked(bulkDeleteFolders);
const mockCleanupTranscoder = vi.mocked(cleanupTranscoder);

const defaultRoots: FileRoot[] = [
	{ key: 'raw', label: 'Raw', path: '/media/raw', writable: true },
	{ key: 'completed', label: 'Completed', path: '/media/completed', writable: true }
];

function file(name: string, extra: Partial<FileEntry> = {}): FileEntry {
	return { name, type: 'file', extension: 'mkv', category: 'video', permissions: 'rw-r--r--', ...extra };
}

function folder(name: string, extra: Partial<FileEntry> = {}): FileEntry {
	return { name, type: 'directory', category: 'directory', permissions: 'rwxr-xr-x', ...extra };
}

function listing(entries: FileEntry[], extra: Partial<DirectoryListing> = {}): DirectoryListing {
	return { root: 'raw', subpath: '', parent_subpath: null, readonly: false, entries, ...extra };
}

// Directory listings the mocked fetchDirectory serves, keyed `root::subpath`.
let dirs: Record<string, DirectoryListing>;

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((r) => (resolve = r));
	return { promise, resolve };
}

function orphans(...names: string[]): OrphanFoldersResponse {
	return {
		total_size_bytes: 1000,
		folders: names.map((name) => ({ path: `/media/raw/${name}`, name, size_bytes: 1000, category: 'raw' }))
	};
}

beforeEach(() => {
	(features as { maintenance: boolean }).maintenance = true;
	setUrl('http://localhost/files');
	setRole('admin');
	dirs = {
		'raw::': listing([file('movie.mkv', { size: 1000 }), folder('subfolder'), file('show.mkv', { size: 500 })])
	};
	mockFetchRoots.mockReset().mockImplementation(() => Promise.resolve(defaultRoots.map((r) => ({ ...r }))));
	mockFetchDirectory
		.mockReset()
		.mockImplementation((root, subpath = '') => Promise.resolve(dirs[`${root}::${subpath}`] ?? listing([])));
	mockRename.mockReset().mockResolvedValue({ root: 'raw', subpath: 'x' });
	mockMove.mockReset().mockResolvedValue({ root: 'raw', subpath: 'x' });
	mockDelete.mockReset().mockResolvedValue({ deleted: true } as never);
	mockCreateDirectory.mockReset().mockResolvedValue({ root: 'raw', subpath: 'x' });
	mockFixPermissions.mockReset().mockResolvedValue({ fixed: 3 } as never);
	mockFetchOrphans.mockReset().mockResolvedValue(orphans());
	mockDeleteOrphan.mockReset().mockResolvedValue({ success: true, path: '' });
	mockBulkDeleteOrphans.mockReset().mockResolvedValue({ removed: [], errors: [] });
	mockCleanupTranscoder.mockReset().mockResolvedValue({ deleted: 0, errors: [] });
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

async function renderPage(firstName = 'movie.mkv') {
	renderComponent(FilesPage);
	await screen.findByText(firstName);
}

function row(name: string): HTMLElement {
	return screen.getByText(name).closest('tr') as HTMLElement;
}

async function selectRow(name: string) {
	await fireEvent.click(within(row(name)).getByRole('checkbox'));
}

function rowNames(): string[] {
	return Array.from(document.querySelectorAll('.file-row-name')).map((n) => n.textContent ?? '');
}

function tabNames(): string[] {
	const group = screen.getByRole('group', { name: 'File root tabs' });
	return within(group)
		.getAllByRole('button')
		.map((b) => b.textContent?.trim() ?? '');
}

const clickButton = (name: string | RegExp) => fireEvent.click(screen.getByRole('button', { name }));

describe('sorting', () => {
	const entries = [
		file('b.mkv', { size: 200, modified: '2025-01-02T00:00:00Z' }),
		folder('zdir', { modified: '2025-02-01T00:00:00Z' }),
		file('nosize.mkv'),
		file('a.mkv', { size: 300, modified: '2025-01-03T00:00:00Z' }),
		folder('adir', { modified: '2025-03-01T00:00:00Z' }),
		file('c.mkv', { size: 100, modified: '2025-01-01T00:00:00Z' }),
		file('nodata.mkv')
	];
	const sortButton = (label: string) => screen.getByRole('button', { name: new RegExp(`^${label}`) });

	beforeEach(() => {
		dirs['raw::'] = listing(entries);
	});

	it('starts on Name ascending with directories first', async () => {
		await renderPage('b.mkv');
		expect(rowNames()).toEqual(['adir', 'zdir', 'a.mkv', 'b.mkv', 'c.mkv', 'nodata.mkv', 'nosize.mkv']);
	});

	it('sorts names case-insensitively', async () => {
		dirs['raw::'] = listing([file('b.mkv'), file('A.mkv'), file('c.mkv')]);
		await renderPage('b.mkv');
		expect(rowNames()).toEqual(['A.mkv', 'b.mkv', 'c.mkv']);
	});

	it('flips Name to descending on a second click, still directories first, and back', async () => {
		await renderPage('b.mkv');
		await fireEvent.click(sortButton('Name'));
		expect(rowNames()).toEqual(['zdir', 'adir', 'nosize.mkv', 'nodata.mkv', 'c.mkv', 'b.mkv', 'a.mkv']);
		await fireEvent.click(sortButton('Name'));
		expect(rowNames()).toEqual(['adir', 'zdir', 'a.mkv', 'b.mkv', 'c.mkv', 'nodata.mkv', 'nosize.mkv']);
	});

	it('sorts Size ascending first, a missing size counting as zero, then descending', async () => {
		await renderPage('b.mkv');
		await fireEvent.click(sortButton('Size'));
		expect(rowNames()).toEqual(['zdir', 'adir', 'nosize.mkv', 'nodata.mkv', 'c.mkv', 'b.mkv', 'a.mkv']);
		await fireEvent.click(sortButton('Size'));
		expect(rowNames()).toEqual(['zdir', 'adir', 'a.mkv', 'b.mkv', 'c.mkv', 'nosize.mkv', 'nodata.mkv']);
	});

	it('starts Modified descending, a missing date sorting last, then ascending', async () => {
		await renderPage('b.mkv');
		await fireEvent.click(sortButton('Modified'));
		expect(rowNames()).toEqual(['adir', 'zdir', 'a.mkv', 'b.mkv', 'c.mkv', 'nosize.mkv', 'nodata.mkv']);
		await fireEvent.click(sortButton('Modified'));
		expect(rowNames()).toEqual(['zdir', 'adir', 'nosize.mkv', 'nodata.mkv', 'c.mkv', 'b.mkv', 'a.mkv']);
	});

	it('restarts a newly chosen column ascending, Name after Modified included', async () => {
		await renderPage('b.mkv');
		await fireEvent.click(sortButton('Modified'));
		await fireEvent.click(sortButton('Name'));
		expect(rowNames()).toEqual(['adir', 'zdir', 'a.mkv', 'b.mkv', 'c.mkv', 'nodata.mkv', 'nosize.mkv']);
	});

	it('shows the sort indicator on the active column only', async () => {
		await renderPage('b.mkv');
		const indicators = () =>
			['Name', 'Size', 'Modified'].map((l) => sortButton(l).querySelectorAll('svg.table-sort-indicator').length);
		expect(indicators()).toEqual([1, 0, 0]);
		await fireEvent.click(sortButton('Size'));
		expect(indicators()).toEqual([0, 1, 0]);
		await fireEvent.click(sortButton('Modified'));
		expect(indicators()).toEqual([0, 0, 1]);
	});
});

describe('roots', () => {
	it('orders tabs raw, transcode, completed, music, then unknown keys and keyless roots', async () => {
		mockFetchRoots.mockResolvedValue([
			{ key: 'zeta', label: 'Zeta', path: '/z', writable: true },
			{ key: 'music', label: 'Music', path: '/m', writable: true },
			{ label: 'Keyless', path: '/k', writable: true } as unknown as FileRoot,
			{ key: 'completed', label: 'Completed', path: '/c', writable: true },
			{ key: 'raw', label: 'Raw', path: '/r', writable: true },
			{ key: 'transcode', label: 'Transcode', path: '/t', writable: true }
		]);
		renderComponent(FilesPage);
		await screen.findByRole('group', { name: 'File root tabs' });
		expect(tabNames()).toEqual(['Raw', 'Transcode', 'Completed', 'Music', 'Zeta', 'Keyless']);
	});

	it.each([
		['before', 0],
		['after', 1]
	])('sorts a keyless root last when it comes %s a keyed one', async (_, at) => {
		const keyless = { label: 'Keyless', path: '/k', writable: true } as unknown as FileRoot;
		const raw = { key: 'raw', label: 'Raw', path: '/r', writable: true };
		mockFetchRoots.mockResolvedValue(at === 0 ? [keyless, raw] : [raw, keyless]);
		renderComponent(FilesPage);
		await screen.findByRole('group', { name: 'File root tabs' });
		expect(tabNames()).toEqual(['Raw', 'Keyless']);
	});

	it('picks the first root when none is in the URL', async () => {
		mockFetchRoots.mockResolvedValue([
			{ key: 'music', label: 'Music', path: '/m', writable: true },
			{ key: 'raw', label: 'Raw', path: '/r', writable: true }
		]);
		renderComponent(FilesPage);
		await waitFor(() => expect(mockFetchDirectory).toHaveBeenCalledWith('raw', ''));
		expect(mockFetchDirectory).not.toHaveBeenCalledWith('music', '');
	});

	it('marks the active root tab as pressed', async () => {
		await renderPage();
		const group = screen.getByRole('group', { name: 'File root tabs' });
		expect(within(group).getByRole('button', { name: 'Raw' })).toHaveAttribute('aria-pressed', 'true');
		expect(within(group).getByRole('button', { name: 'Completed' })).toHaveAttribute('aria-pressed', 'false');
	});

	it('opens the root and subpath given as ?root= and ?subpath= on mount', async () => {
		dirs['completed::a/b'] = listing([file('deep.mkv')], { root: 'completed', subpath: 'a/b' });
		setUrl('http://localhost/files?root=completed&subpath=a/b');
		await renderPage('deep.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('completed', 'a/b');
		expect(mockFetchDirectory).not.toHaveBeenCalledWith('raw', '');
	});

	it('opens the root folder when only ?root= is given', async () => {
		setUrl('http://localhost/files?root=completed');
		renderComponent(FilesPage);
		await waitFor(() => expect(mockFetchDirectory).toHaveBeenCalledWith('completed', ''));
	});

	it('ignores an empty ?root=', async () => {
		setUrl('http://localhost/files?root=');
		await renderPage();
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
	});

	it('follows ?root= and ?subpath= when they change after mount', async () => {
		dirs['completed::x'] = listing([file('later.mkv')], { root: 'completed', subpath: 'x' });
		await renderPage();
		setUrl('http://localhost/files?root=completed&subpath=x');
		await screen.findByText('later.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('completed', 'x');
	});

	it('does not reload when the same params arrive twice', async () => {
		dirs['completed::x'] = listing([file('x.mkv')], { root: 'completed', subpath: 'x' });
		setUrl('http://localhost/files?root=completed&subpath=x');
		await renderPage('x.mkv');
		const calls = mockFetchDirectory.mock.calls.length;
		setUrl('http://localhost/files?root=completed&subpath=x');
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchDirectory.mock.calls.length).toBe(calls);
	});

	it('shows no tabs and does not list when there are no roots', async () => {
		mockFetchRoots.mockResolvedValue([]);
		renderComponent(FilesPage);
		await waitFor(() => expect(mockFetchRoots).toHaveBeenCalled());
		await waitFor(() => expect(document.querySelectorAll('tr[aria-busy="true"]').length).toBe(8));
		expect(screen.queryByRole('group', { name: 'File root tabs' })).not.toBeInTheDocument();
		expect(mockFetchDirectory).not.toHaveBeenCalled();
	});

	it('shows a generic message when the roots call fails with a non-Error', async () => {
		mockFetchRoots.mockRejectedValueOnce('nope');
		renderComponent(FilesPage);
		expect(await screen.findByText('Failed to load roots')).toBeInTheDocument();
	});

	it('shows a generic message when a directory call fails with a non-Error', async () => {
		mockFetchDirectory.mockRejectedValueOnce('nope');
		renderComponent(FilesPage);
		expect(await screen.findByText('Failed to load directory')).toBeInTheDocument();
	});
});

describe('listing states', () => {
	it('shows the loading skeleton while the directory is pending', async () => {
		const pending = deferred<DirectoryListing>();
		mockFetchDirectory.mockReturnValueOnce(pending.promise);
		renderComponent(FilesPage);
		await waitFor(() => expect(document.querySelectorAll('tr[aria-busy="true"]').length).toBe(8));
		expect(await screen.findByTitle('Refresh')).toBeDisabled();
		pending.resolve(dirs['raw::']);
		await screen.findByText('movie.mkv');
		expect(document.querySelectorAll('tr[aria-busy="true"]').length).toBe(0);
	});

	it('shows the empty folder state', async () => {
		dirs['raw::'] = listing([]);
		renderComponent(FilesPage);
		expect(await screen.findByText('This directory is empty')).toBeInTheDocument();
	});

	it('shows neither the empty message nor a table for an empty folder with a new-folder row open', async () => {
		dirs['raw::'] = listing([]);
		renderComponent(FilesPage);
		await screen.findByText('This directory is empty');
		await clickButton('New folder');
		expect(screen.getByPlaceholderText('Folder name')).toBeInTheDocument();
		expect(screen.queryByText('This directory is empty')).not.toBeInTheDocument();
		expect(screen.queryByRole('table')).not.toBeInTheDocument();
	});

	it('shows the read-only banner and disables the write controls on a read-only mount', async () => {
		dirs['raw::'] = listing([file('movie.mkv', { size: 1 })], { readonly: true });
		await renderPage();
		expect(
			screen.getByText('This directory is on a read-only mount. File operations are disabled.')
		).toBeInTheDocument();
		const toolbar = document.querySelector('.files-page-toolbar') as HTMLElement;
		expect(within(toolbar).getByTitle('Read-only mount')).toBeDisabled();
		const rowButtons = within(row('movie.mkv')).getAllByTitle('Read-only mount');
		expect(rowButtons).toHaveLength(3);
		rowButtons.forEach((b) => expect(b).toBeDisabled());
		await selectRow('movie.mkv');
		expect(screen.getByRole('button', { name: /^Move 1$/ })).toBeDisabled();
		expect(screen.getByRole('button', { name: /^Delete 1$/ })).toBeDisabled();
	});

	it('shows no read-only banner on a writable mount', async () => {
		await renderPage();
		expect(screen.queryByText(/read-only mount/)).not.toBeInTheDocument();
	});

	it('goes up through the .. row when the listing has a parent', async () => {
		dirs['raw::a'] = listing([file('inner.mkv')], { subpath: 'a', parent_subpath: '' });
		setUrl('http://localhost/files?root=raw&subpath=a');
		await renderPage('inner.mkv');
		await fireEvent.click(screen.getByRole('button', { name: '..' }));
		await screen.findByText('movie.mkv');
		expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', '');
	});

	it('shows no .. row at the top of a root', async () => {
		await renderPage();
		expect(screen.queryByRole('button', { name: '..' })).not.toBeInTheDocument();
	});

	it('refreshes the current directory from the toolbar', async () => {
		await renderPage();
		mockFetchDirectory.mockClear();
		await fireEvent.click(screen.getByTitle('Refresh'));
		await waitFor(() => expect(mockFetchDirectory).toHaveBeenCalledWith('raw', ''));
	});

	it('navigates when a breadcrumb is clicked', async () => {
		dirs['raw::a'] = listing([file('inner.mkv')], { subpath: 'a', parent_subpath: '' });
		setUrl('http://localhost/files?root=raw&subpath=a');
		await renderPage('inner.mkv');
		const nav = document.querySelector('nav.breadcrumb') as HTMLElement;
		await fireEvent.click(within(nav).getByRole('button', { name: 'Raw' }));
		await screen.findByText('movie.mkv');
		expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', '');
	});
});

describe('selection', () => {
	it('selects one row and shows the bulk buttons with its count', async () => {
		await renderPage();
		await selectRow('movie.mkv');
		expect(screen.getByRole('button', { name: /^Move 1$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Delete 1$/ })).toBeInTheDocument();
		await selectRow('movie.mkv');
		expect(screen.queryByRole('button', { name: /^Move 1$/ })).not.toBeInTheDocument();
	});

	it('selects everything with the header checkbox and clears it with a second click', async () => {
		await renderPage();
		const all = document.querySelector('thead input[type="checkbox"]') as HTMLInputElement;
		await fireEvent.click(all);
		expect(screen.getByRole('button', { name: /^Move 3$/ })).toBeInTheDocument();
		expect(all.checked).toBe(true);
		await fireEvent.click(all);
		expect(screen.queryByRole('button', { name: /^Move \d+$/ })).not.toBeInTheDocument();
		expect(all.checked).toBe(false);
	});

	it('clears the selection when navigating into a folder', async () => {
		await renderPage();
		await selectRow('movie.mkv');
		await fireEvent.click(screen.getByText('subfolder'));
		await waitFor(() => expect(mockFetchDirectory).toHaveBeenCalledWith('raw', 'subfolder'));
		await waitFor(() => expect(screen.queryByRole('button', { name: /^Move \d+$/ })).not.toBeInTheDocument());
	});

	it('ignores the header checkbox once the listing is gone', async () => {
		await renderPage();
		const all = document.querySelector('thead input[type="checkbox"]') as HTMLInputElement;
		mockFetchDirectory.mockRejectedValueOnce(new Error('gone'));
		await fireEvent.click(screen.getByTitle('Refresh'));
		await screen.findByText('gone');
		// Svelte delegates change on the document, so re-attach the removed checkbox to reach its handler.
		document.body.appendChild(all);
		all.dispatchEvent(new Event('change', { bubbles: true }));
		await new Promise((r) => setTimeout(r, 20));
		expect(screen.queryByRole('button', { name: /^Move \d+$/ })).not.toBeInTheDocument();
	});
});

describe('rename', () => {
	async function rename(from: string, to: string) {
		const target = row(from);
		await fireEvent.click(within(target).getByTitle('Rename'));
		const input = within(target).getByRole('textbox');
		await fireEvent.input(input, { target: { value: to } });
		await fireEvent.keyDown(input, { key: 'Enter' });
	}

	it('renames a row, reports it and reloads the listing', async () => {
		await renderPage();
		mockFetchDirectory.mockClear();
		await rename('movie.mkv', 'film.mkv');
		expect(await screen.findByText('Renamed to film.mkv')).toHaveClass('alert-success');
		expect(mockRename).toHaveBeenCalledWith('raw', 'movie.mkv', 'film.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
	});

	it('renames inside a subfolder using the full item path', async () => {
		dirs['raw::a'] = listing([file('inner.mkv')], { subpath: 'a', parent_subpath: '' });
		setUrl('http://localhost/files?root=raw&subpath=a');
		await renderPage('inner.mkv');
		await rename('inner.mkv', 'outer.mkv');
		await screen.findByText('Renamed to outer.mkv');
		expect(mockRename).toHaveBeenCalledWith('raw', 'a/inner.mkv', 'outer.mkv');
	});

	it('shows the Error message when renaming fails', async () => {
		mockRename.mockRejectedValueOnce(new Error('Name taken'));
		await renderPage();
		await rename('movie.mkv', 'film.mkv');
		expect(await screen.findByText('Name taken')).toHaveClass('alert-danger');
	});

	it('shows a generic message when renaming fails with a non-Error', async () => {
		mockRename.mockRejectedValueOnce('nope');
		await renderPage();
		await rename('movie.mkv', 'film.mkv');
		expect(await screen.findByText('Rename failed')).toHaveClass('alert-danger');
	});

	it('clears the feedback after 3 seconds', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		await renderPage();
		await rename('movie.mkv', 'film.mkv');
		await screen.findByText('Renamed to film.mkv');
		await vi.advanceTimersByTimeAsync(2900);
		expect(screen.getByText('Renamed to film.mkv')).toBeInTheDocument();
		await vi.advanceTimersByTimeAsync(200);
		await waitFor(() => expect(screen.queryByText('Renamed to film.mkv')).not.toBeInTheDocument());
	});
});

describe('fix permissions', () => {
	const fix = (name: string) => fireEvent.click(within(row(name)).getByTitle('Fix permissions'));

	it('reports the plural item count', async () => {
		await renderPage();
		mockFetchDirectory.mockClear();
		await fix('movie.mkv');
		expect(await screen.findByText('Fixed permissions on movie.mkv (3 items)')).toHaveClass('alert-success');
		expect(mockFixPermissions).toHaveBeenCalledWith('raw', 'movie.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
	});

	it('reports a single item without a plural s', async () => {
		mockFixPermissions.mockResolvedValueOnce({ fixed: 1 } as never);
		await renderPage();
		await fix('movie.mkv');
		expect(await screen.findByText('Fixed permissions on movie.mkv (1 item)')).toBeInTheDocument();
	});

	it('shows the Error message when it fails', async () => {
		mockFixPermissions.mockRejectedValueOnce(new Error('Not permitted'));
		await renderPage();
		await fix('movie.mkv');
		expect(await screen.findByText('Not permitted')).toHaveClass('alert-danger');
	});

	it('shows a generic message when it fails with a non-Error', async () => {
		mockFixPermissions.mockRejectedValueOnce('nope');
		await renderPage();
		await fix('movie.mkv');
		expect(await screen.findByText('Failed to fix permissions')).toHaveClass('alert-danger');
	});
});

describe('delete one item', () => {
	async function openDelete(name: string) {
		await fireEvent.click(within(row(name)).getByTitle('Delete'));
		return screen.findByRole('dialog');
	}

	it('asks first, then deletes through the dialog and reloads', async () => {
		await renderPage();
		const dialog = await openDelete('movie.mkv');
		expect(within(dialog).getByText('Delete movie.mkv')).toBeInTheDocument();
		expect(
			within(dialog).getByText("Are you sure you want to delete 'movie.mkv'? This action cannot be undone.")
		).toBeInTheDocument();
		expect(mockDelete).not.toHaveBeenCalled();
		mockFetchDirectory.mockClear();
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
		expect(await screen.findByText('Deleted movie.mkv')).toHaveClass('alert-success');
		expect(mockDelete).toHaveBeenCalledWith('raw', 'movie.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
	});

	it('deletes nothing when the dialog is cancelled', async () => {
		await renderPage();
		const dialog = await openDelete('movie.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(mockDelete).not.toHaveBeenCalled();
	});

	it('keeps the dialog open and shows the Error message when the delete fails', async () => {
		mockDelete.mockRejectedValueOnce(new Error('In use'));
		await renderPage();
		const dialog = await openDelete('movie.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
		expect(await screen.findByText('In use')).toHaveClass('alert-danger');
		expect(screen.getByRole('dialog')).toBeInTheDocument();
	});

	it('shows a generic message when the delete fails with a non-Error', async () => {
		mockDelete.mockRejectedValueOnce('nope');
		await renderPage();
		const dialog = await openDelete('movie.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
		expect(await screen.findByText('Delete failed')).toBeInTheDocument();
	});

	it('uses the full item path for a delete inside a subfolder', async () => {
		dirs['raw::a'] = listing([file('inner.mkv')], { subpath: 'a', parent_subpath: '' });
		setUrl('http://localhost/files?root=raw&subpath=a');
		await renderPage('inner.mkv');
		const dialog = await openDelete('inner.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
		await screen.findByText('Deleted inner.mkv');
		expect(mockDelete).toHaveBeenCalledWith('raw', 'a/inner.mkv');
	});
});

describe('new folder', () => {
	async function startFolder(text?: string) {
		await clickButton('New folder');
		const input = screen.getByPlaceholderText('Folder name');
		if (text !== undefined) await fireEvent.input(input, { target: { value: text } });
		return input;
	}

	it('creates the trimmed name on Enter, reports it and reloads', async () => {
		await renderPage();
		mockFetchDirectory.mockClear();
		const input = await startFolder('  docs  ');
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(await screen.findByText('Created folder "docs"')).toHaveClass('alert-success');
		expect(mockCreateDirectory).toHaveBeenCalledWith('raw', '', 'docs');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
		await waitFor(() => expect(screen.queryByPlaceholderText('Folder name')).not.toBeInTheDocument());
	});

	it('creates through the Create button', async () => {
		await renderPage();
		await startFolder('docs');
		await fireEvent.click(screen.getByTitle('Create'));
		await screen.findByText('Created folder "docs"');
		expect(mockCreateDirectory).toHaveBeenCalledWith('raw', '', 'docs');
	});

	it('cancels on Escape', async () => {
		await renderPage();
		const input = await startFolder('docs');
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.queryByPlaceholderText('Folder name')).not.toBeInTheDocument();
		expect(mockCreateDirectory).not.toHaveBeenCalled();
	});

	it('cancels through the Cancel button and starts blank next time', async () => {
		await renderPage();
		await startFolder('docs');
		await fireEvent.click(within(screen.getByPlaceholderText('Folder name').parentElement!).getByTitle('Cancel'));
		expect(screen.queryByPlaceholderText('Folder name')).not.toBeInTheDocument();
		await clickButton('New folder');
		expect(screen.getByPlaceholderText('Folder name')).toHaveValue('');
	});

	it('ignores a blank name', async () => {
		await renderPage();
		const input = await startFolder('   ');
		await fireEvent.keyDown(input, { key: 'Enter' });
		await fireEvent.click(screen.getByTitle('Create'));
		expect(mockCreateDirectory).not.toHaveBeenCalled();
		expect(screen.getByPlaceholderText('Folder name')).toBeInTheDocument();
	});

	it('ignores other keys', async () => {
		await renderPage();
		const input = await startFolder('docs');
		await fireEvent.keyDown(input, { key: 'a' });
		expect(mockCreateDirectory).not.toHaveBeenCalled();
		expect(screen.getByPlaceholderText('Folder name')).toBeInTheDocument();
	});

	it('creates inside the current subfolder', async () => {
		dirs['raw::a'] = listing([file('inner.mkv')], { subpath: 'a', parent_subpath: '' });
		setUrl('http://localhost/files?root=raw&subpath=a');
		await renderPage('inner.mkv');
		const input = await startFolder('docs');
		await fireEvent.keyDown(input, { key: 'Enter' });
		await screen.findByText('Created folder "docs"');
		expect(mockCreateDirectory).toHaveBeenCalledWith('raw', 'a', 'docs');
	});

	it('shows the Error message and keeps the row when creating fails', async () => {
		mockCreateDirectory.mockRejectedValueOnce(new Error('Exists'));
		await renderPage();
		const input = await startFolder('docs');
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(await screen.findByText('Exists')).toHaveClass('alert-danger');
		expect(screen.getByPlaceholderText('Folder name')).toBeInTheDocument();
	});

	it('shows a generic message when creating fails with a non-Error', async () => {
		mockCreateDirectory.mockRejectedValueOnce('nope');
		await renderPage();
		const input = await startFolder('docs');
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(await screen.findByText('Failed to create folder')).toBeInTheDocument();
	});
});

describe('bulk move picker', () => {
	const pickerPath = () => document.querySelector('.files-page-picker-path')?.textContent;
	const moveButton = () => screen.getByRole('button', { name: 'Move here' });
	const pickerPanel = () => document.querySelector('.modal .files-page-orphan-panel') as HTMLElement;
	const pickerFolder = (name: string) =>
		waitFor(() => {
			const el = Array.from(pickerPanel().querySelectorAll('.files-page-picker-row-folder')).find(
				(b) => b.textContent?.trim() === name
			);
			expect(el).toBeTruthy();
			return el as HTMLElement;
		});
	const pickerUp = () => within(pickerPanel()).getByRole('button', { name: '..' });

	beforeEach(() => {
		dirs['raw::'] = listing([
			file('movie.mkv', { size: 1 }),
			file('show.mkv', { size: 1 }),
			folder('subfolder'),
			folder('other')
		]);
		dirs['raw::other'] = listing([folder('inner')], { subpath: 'other', parent_subpath: '' });
	});

	async function openPicker(...names: string[]) {
		await renderPage();
		for (const n of names) await selectRow(n);
		await fireEvent.click(screen.getByRole('button', { name: /^Move \d+$/ }));
		await screen.findByText('Browse to the destination folder');
	}

	it('opens at the current folder, marked current, with Move here disabled', async () => {
		await openPicker('movie.mkv');
		expect(screen.getByText('Move 1 item')).toBeInTheDocument();
		await waitFor(() => expect(pickerPath()).toBe('Raw'));
		expect(screen.getByText('current')).toBeInTheDocument();
		expect(moveButton()).toBeDisabled();
		expect(moveButton()).toHaveAttribute('title', 'Navigate to a different folder first');
		const names = Array.from(document.querySelectorAll('.files-page-picker-row-folder')).map((b) =>
			b.textContent?.trim()
		);
		expect(names).toEqual(['subfolder', 'other']);
		expect(screen.queryByText('No subfolders')).not.toBeInTheDocument();
	});

	it('hides a selected folder from the picker while it browses the source folder', async () => {
		await renderPage();
		await selectRow('subfolder');
		await fireEvent.click(screen.getByRole('button', { name: /^Move \d+$/ }));
		await screen.findByText('Browse to the destination folder');
		const names = Array.from(document.querySelectorAll('.files-page-picker-row-folder')).map((b) =>
			b.textContent?.trim()
		);
		expect(names).toEqual(['other']);
	});

	it('does nothing when Move is clicked after the selection was just cleared', async () => {
		await renderPage();
		await selectRow('movie.mkv');
		const move = screen.getByRole('button', { name: /^Move 1$/ });
		mockFetchDirectory.mockClear();
		// Both clicks land before Svelte flushes, so the stale button is still in the DOM.
		within(row('movie.mkv')).getByRole('checkbox').click();
		move.click();
		await new Promise((r) => setTimeout(r, 20));
		expect(screen.queryByText('Browse to the destination folder')).not.toBeInTheDocument();
		expect(mockFetchDirectory).not.toHaveBeenCalled();
	});

	it('browses into a folder, then enables Move here and drops the current marker', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', 'other');
		expect(screen.queryByText('current')).not.toBeInTheDocument();
		expect(moveButton()).toBeEnabled();
		expect(moveButton()).toHaveAttribute('title', '');
		expect(within(pickerPanel()).getByRole('button', { name: /inner/ })).toBeInTheDocument();
	});

	it('browses a nested folder by joining the picker subpath', async () => {
		dirs['raw::other/inner'] = listing([], { subpath: 'other/inner', parent_subpath: 'other' });
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await fireEvent.click(await pickerFolder('inner'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other/inner'));
		expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', 'other/inner');
	});

	it('goes up within the root with the .. row', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		await fireEvent.click(pickerUp());
		await waitFor(() => expect(pickerPath()).toBe('Raw'));
		expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', '');
	});

	it('does nothing when .. is pressed with the picker already at the top', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		const up = pickerUp();
		await fireEvent.click(up);
		await waitFor(() => expect(pickerPath()).toBe('Raw'));
		expect(within(pickerPanel()).queryByRole('button', { name: '..' })).not.toBeInTheDocument();
		mockFetchDirectory.mockClear();
		// Svelte delegates click on the document, so re-attach the removed button to reach its handler.
		document.body.appendChild(up);
		up.click();
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchDirectory).not.toHaveBeenCalled();
		expect(pickerPath()).toBe('Raw');
	});

	it('does nothing when .. is pressed on a listing with no parent, below the top of the root', async () => {
		dirs['raw::other'] = listing([], { subpath: 'other', parent_subpath: null });
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		mockFetchDirectory.mockClear();
		await fireEvent.click(pickerUp());
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchDirectory).not.toHaveBeenCalled();
		expect(pickerPath()).toBe('Raw/other');
	});

	it('does nothing when .. is pressed at the top of a root other than the current one', async () => {
		dirs['completed::'] = listing([file('c.mkv')], { root: 'completed' });
		await openPicker('movie.mkv');
		setUrl('http://localhost/files?root=completed');
		await screen.findByText('c.mkv');
		await waitFor(() => expect(pickerUp()).toBeInTheDocument());
		mockFetchDirectory.mockClear();
		await fireEvent.click(pickerUp());
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchDirectory).not.toHaveBeenCalled();
		expect(pickerPath()).toBe('Raw');
	});

	it('keeps the listing when browsing into a folder fails', async () => {
		await openPicker('movie.mkv');
		const other = await pickerFolder('other');
		mockFetchDirectory.mockRejectedValueOnce(new Error('denied'));
		await fireEvent.click(other);
		await waitFor(() => expect(mockFetchDirectory).toHaveBeenLastCalledWith('raw', 'other'));
		await waitFor(() => expect(within(pickerPanel()).queryByRole('button', { name: /other/ })).toBeInTheDocument());
		expect(pickerPath()).toBe('Raw');
		expect(within(pickerPanel()).getByRole('button', { name: /subfolder/ })).toBeInTheDocument();
	});

	it('shows No subfolders when the first picker load fails', async () => {
		await renderPage();
		await selectRow('movie.mkv');
		mockFetchDirectory.mockRejectedValueOnce(new Error('denied'));
		await fireEvent.click(screen.getByRole('button', { name: /^Move 1$/ }));
		expect(await screen.findByText('No subfolders')).toBeInTheDocument();
		expect(pickerPath()).toBe('Raw');
	});

	it('shows a spinner instead of folders while the picker loads', async () => {
		await renderPage();
		await selectRow('movie.mkv');
		const pending = deferred<DirectoryListing>();
		mockFetchDirectory.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: /^Move 1$/ }));
		await screen.findByText('Browse to the destination folder');
		expect(document.querySelector('.modal .spin')).toBeInTheDocument();
		expect(screen.queryByText('No subfolders')).not.toBeInTheDocument();
		pending.resolve(dirs['raw::']);
		await waitFor(() => expect(document.querySelector('.modal .spin')).not.toBeInTheDocument());
	});

	it('labels an unknown root by its key', async () => {
		dirs['ghost::'] = listing([file('boo.mkv')], { root: 'ghost' });
		setUrl('http://localhost/files?root=ghost');
		await renderPage('boo.mkv');
		await selectRow('boo.mkv');
		await fireEvent.click(screen.getByRole('button', { name: /^Move 1$/ }));
		await screen.findByText('Browse to the destination folder');
		expect(pickerPath()).toBe('ghost');
	});

	it('moves every selected item to the picked folder and reports the plural count', async () => {
		await openPicker('movie.mkv', 'show.mkv');
		expect(screen.getByText('Move 2 items')).toBeInTheDocument();
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		mockFetchDirectory.mockClear();
		await fireEvent.click(moveButton());
		expect(await screen.findByText('Moved 2 items')).toHaveClass('alert-success');
		expect(mockMove).toHaveBeenCalledTimes(2);
		expect(mockMove).toHaveBeenCalledWith('raw', 'movie.mkv', 'raw', 'other');
		expect(mockMove).toHaveBeenCalledWith('raw', 'show.mkv', 'raw', 'other');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
		expect(screen.queryByText('Browse to the destination folder')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /^Move \d+$/ })).not.toBeInTheDocument();
	});

	it('reports a single move without a plural s', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		await fireEvent.click(moveButton());
		expect(await screen.findByText('Moved 1 item')).toBeInTheDocument();
	});

	it('reports how many moves failed and still moves the rest', async () => {
		mockMove.mockRejectedValueOnce(new Error('busy'));
		await openPicker('movie.mkv', 'show.mkv');
		await fireEvent.click(await pickerFolder('other'));
		await waitFor(() => expect(pickerPath()).toBe('Raw/other'));
		await fireEvent.click(moveButton());
		expect(await screen.findByText('Moved 1, failed 1')).toHaveClass('alert-danger');
		expect(mockMove).toHaveBeenCalledTimes(2);
	});

	it('closes with Cancel without moving anything', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(screen.queryByText('Browse to the destination folder')).not.toBeInTheDocument();
		expect(mockMove).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: /^Move 1$/ })).toBeInTheDocument();
	});

	it('closes by clicking the backdrop', async () => {
		await openPicker('movie.mkv');
		await fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }));
		expect(screen.queryByText('Browse to the destination folder')).not.toBeInTheDocument();
	});
});

describe('bulk delete', () => {
	const openBulk = async (...names: string[]) => {
		for (const n of names) await selectRow(n);
		await fireEvent.click(screen.getByRole('button', { name: /^Delete \d+$/ }));
		return screen.findByRole('dialog');
	};

	it('asks first, then deletes every selected item and reports the plural count', async () => {
		await renderPage();
		const dialog = await openBulk('movie.mkv', 'show.mkv');
		expect(within(dialog).getByText('Delete 2 items')).toBeInTheDocument();
		expect(
			within(dialog).getByText(
				'This will permanently delete 2 selected items, including all contents of any folders. This cannot be undone.'
			)
		).toBeInTheDocument();
		expect(mockDelete).not.toHaveBeenCalled();
		mockFetchDirectory.mockClear();
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete All' }));
		expect(await screen.findByText('Deleted 2 items')).toHaveClass('alert-success');
		expect(mockDelete).toHaveBeenCalledWith('raw', 'movie.mkv');
		expect(mockDelete).toHaveBeenCalledWith('raw', 'show.mkv');
		expect(mockFetchDirectory).toHaveBeenCalledWith('raw', '');
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(screen.queryByRole('button', { name: /^Delete \d+$/ })).not.toBeInTheDocument();
	});

	it('reports a single delete without a plural s', async () => {
		await renderPage();
		const dialog = await openBulk('movie.mkv');
		expect(within(dialog).getByText('Delete 1 item')).toBeInTheDocument();
		expect(within(dialog).getByText(/permanently delete 1 selected item, including/)).toBeInTheDocument();
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete All' }));
		expect(await screen.findByText('Deleted 1 item')).toBeInTheDocument();
	});

	it('deletes children before their parents', async () => {
		// Only names containing a slash can be both selected and nested in one listing.
		dirs['raw::'] = listing([folder('docs'), file('docs/ep1.mkv'), file('other.mkv')]);
		await renderPage('other.mkv');
		const all = document.querySelector('thead input[type="checkbox"]') as HTMLInputElement;
		await fireEvent.click(all);
		await fireEvent.click(screen.getByRole('button', { name: /^Delete 3$/ }));
		const dialog = await screen.findByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete All' }));
		expect(await screen.findByText('Deleted 3 items')).toBeInTheDocument();
		expect(mockDelete.mock.calls.map((c) => c[1])).toEqual(['docs/ep1.mkv', 'other.mkv', 'docs']);
	});

	it('reports how many deletes failed and still deletes the rest', async () => {
		mockDelete.mockRejectedValueOnce(new Error('busy'));
		await renderPage();
		const dialog = await openBulk('movie.mkv', 'show.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Delete All' }));
		expect(await screen.findByText('Deleted 1, failed 1')).toHaveClass('alert-danger');
		expect(mockDelete).toHaveBeenCalledTimes(2);
	});

	it('deletes nothing when the dialog is cancelled', async () => {
		await renderPage();
		const dialog = await openBulk('movie.mkv');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(mockDelete).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: /^Delete 1$/ })).toBeInTheDocument();
	});
});

describe('orphan folders modal', () => {
	async function openModal() {
		await renderPage();
		await fireEvent.click(screen.getByTitle('Orphan folders'));
		await screen.findByText('Orphan Folders');
	}
	const modal = () => document.querySelector('.files-page-orphan-panel') as HTMLElement;
	const modalCheckboxes = () => within(modal()).queryAllByRole('checkbox');

	it('shows a loading message while the folders load', async () => {
		const pending = deferred<OrphanFoldersResponse>();
		mockFetchOrphans.mockReturnValueOnce(pending.promise);
		await openModal();
		expect(screen.getByText('Loading...')).toBeInTheDocument();
		pending.resolve(orphans('one'));
		expect(await screen.findByText('one')).toBeInTheDocument();
		expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
	});

	it('says so when the folders fail to load', async () => {
		mockFetchOrphans.mockRejectedValueOnce(new Error('down'));
		await openModal();
		expect(await screen.findByText('Failed to load orphan folders')).toBeInTheDocument();
	});

	it('says so when there are no orphan folders', async () => {
		await openModal();
		expect(await screen.findByText('No orphan folders found')).toBeInTheDocument();
	});

	it('lists each folder with its size and category', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		await openModal();
		expect(await screen.findByText('one')).toBeInTheDocument();
		expect(within(modal()).getByText('raw')).toBeInTheDocument();
	});

	it('selects and unselects a folder, showing the bulk button while one is selected', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one', 'two'));
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		expect(screen.getByRole('button', { name: 'Delete 1 selected' })).toBeInTheDocument();
		await fireEvent.click(modalCheckboxes()[1]);
		expect(screen.getByRole('button', { name: 'Delete 2 selected' })).toBeInTheDocument();
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(modalCheckboxes()[1]);
		expect(screen.queryByRole('button', { name: /selected$/ })).not.toBeInTheDocument();
	});

	it('deletes one folder, reports it and reloads the list', async () => {
		mockFetchOrphans.mockResolvedValueOnce(orphans('one', 'two')).mockResolvedValueOnce(orphans('two'));
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[1]);
		await fireEvent.click(within(modal()).getAllByTitle('Delete folder')[0]);
		expect(await screen.findByText('Folder "one" deleted')).toHaveClass('alert-success');
		expect(mockDeleteOrphan).toHaveBeenCalledWith('/media/raw/one');
		expect(mockFetchOrphans).toHaveBeenCalledTimes(2);
		await waitFor(() => expect(screen.queryByText('one')).not.toBeInTheDocument());
		expect(screen.queryByRole('button', { name: /selected$/ })).not.toBeInTheDocument();
	});

	it('shows the Error message when deleting one folder fails', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockDeleteOrphan.mockRejectedValueOnce(new Error('locked'));
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(within(modal()).getByTitle('Delete folder'));
		expect(await screen.findByText('locked')).toHaveClass('alert-danger');
		expect(screen.getByText('one')).toBeInTheDocument();
	});

	it('shows a generic message when deleting one folder fails with a non-Error', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockDeleteOrphan.mockRejectedValueOnce('nope');
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(within(modal()).getByTitle('Delete folder'));
		expect(await screen.findByText('Delete failed')).toHaveClass('alert-danger');
	});

	it('bulk deletes the selected folders and reports the plural count', async () => {
		mockFetchOrphans.mockResolvedValueOnce(orphans('one', 'two')).mockResolvedValueOnce(orphans());
		mockBulkDeleteOrphans.mockResolvedValueOnce({ removed: ['a', 'b'], errors: [] });
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(modalCheckboxes()[1]);
		await fireEvent.click(screen.getByRole('button', { name: 'Delete 2 selected' }));
		expect(await screen.findByText('Deleted 2 folders')).toHaveClass('alert-success');
		expect(mockBulkDeleteOrphans).toHaveBeenCalledWith(['/media/raw/one', '/media/raw/two']);
		expect(await screen.findByText('No orphan folders found')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /selected$/ })).not.toBeInTheDocument();
	});

	it('reports a single bulk delete without a plural s', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockBulkDeleteOrphans.mockResolvedValueOnce({ removed: ['a'], errors: [] });
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(screen.getByRole('button', { name: 'Delete 1 selected' }));
		expect(await screen.findByText('Deleted 1 folder')).toBeInTheDocument();
	});

	it('reports the errors from a bulk delete in the error tone', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockBulkDeleteOrphans.mockResolvedValueOnce({ removed: ['a'], errors: ['x'] });
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(screen.getByRole('button', { name: 'Delete 1 selected' }));
		expect(await screen.findByText('Deleted 1 folder, 1 error(s)')).toHaveClass('alert-danger');
	});

	it('shows the Error message when the bulk delete fails', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockBulkDeleteOrphans.mockRejectedValueOnce(new Error('boom'));
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(screen.getByRole('button', { name: 'Delete 1 selected' }));
		expect(await screen.findByText('boom')).toHaveClass('alert-danger');
	});

	it('shows a generic message when the bulk delete fails with a non-Error', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockBulkDeleteOrphans.mockRejectedValueOnce('nope');
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(modalCheckboxes()[0]);
		await fireEvent.click(screen.getByRole('button', { name: 'Delete 1 selected' }));
		expect(await screen.findByText('Bulk delete failed')).toBeInTheDocument();
	});

	it('closes with the Close button and clears the old feedback when reopened', async () => {
		mockFetchOrphans.mockResolvedValue(orphans('one'));
		mockDeleteOrphan.mockRejectedValueOnce(new Error('locked'));
		await openModal();
		await screen.findByText('one');
		await fireEvent.click(within(modal()).getByTitle('Delete folder'));
		await screen.findByText('locked');
		await fireEvent.click(within(modal()).getByRole('button', { name: 'Close' }));
		expect(screen.queryByText('Orphan Folders')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByTitle('Orphan folders'));
		await screen.findByText('one');
		expect(screen.queryByText('locked')).not.toBeInTheDocument();
	});

	it('closes by clicking the backdrop', async () => {
		await openModal();
		await fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }));
		expect(screen.queryByText('Orphan Folders')).not.toBeInTheDocument();
	});
});

describe('transcoder cleanup', () => {
	async function confirmCleanup() {
		await renderPage();
		await fireEvent.click(screen.getByTitle('Clean up transcoder jobs'));
		const dialog = await screen.findByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Clean Up' }));
	}

	it('reports the plural job count and closes the dialog', async () => {
		mockCleanupTranscoder.mockResolvedValueOnce({ deleted: 3, errors: [] });
		await confirmCleanup();
		expect(await screen.findByText('Deleted 3 transcoder jobs')).toHaveClass('alert-success');
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('reports a single job without a plural s', async () => {
		mockCleanupTranscoder.mockResolvedValueOnce({ deleted: 1, errors: [] });
		await confirmCleanup();
		expect(await screen.findByText('Deleted 1 transcoder job')).toBeInTheDocument();
	});

	it('reports the errors in the error tone', async () => {
		mockCleanupTranscoder.mockResolvedValueOnce({ deleted: 2, errors: ['x'] });
		await confirmCleanup();
		expect(await screen.findByText('Deleted 2 transcoder jobs, 1 error(s)')).toHaveClass('alert-danger');
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('shows the Error message and still closes the dialog when it fails', async () => {
		mockCleanupTranscoder.mockRejectedValueOnce(new Error('offline'));
		await confirmCleanup();
		expect(await screen.findByText('offline')).toHaveClass('alert-danger');
		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('shows a generic message when it fails with a non-Error', async () => {
		mockCleanupTranscoder.mockRejectedValueOnce('nope');
		await confirmCleanup();
		expect(await screen.findByText('Cleanup failed')).toBeInTheDocument();
	});

	it('closes without cleaning up when cancelled', async () => {
		await renderPage();
		await fireEvent.click(screen.getByTitle('Clean up transcoder jobs'));
		const dialog = await screen.findByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
		expect(mockCleanupTranscoder).not.toHaveBeenCalled();
	});
});
