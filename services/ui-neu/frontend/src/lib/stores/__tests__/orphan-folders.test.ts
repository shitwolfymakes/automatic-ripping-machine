import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { OrphanFoldersResponse } from '$lib/api/maintenance';

vi.mock('$lib/api/maintenance', () => ({
	fetchOrphanFolders: vi.fn(),
	deleteFolder: vi.fn(),
	bulkDeleteFolders: vi.fn()
}));

import { fetchOrphanFolders, deleteFolder, bulkDeleteFolders } from '$lib/api/maintenance';
import { OrphanFolders } from '../orphan-folders.svelte';

const mockFetch = vi.mocked(fetchOrphanFolders);
const mockDelete = vi.mocked(deleteFolder);
const mockBulk = vi.mocked(bulkDeleteFolders);

const response = (...paths: string[]) =>
	({ folders: paths.map((path) => ({ path, name: path.split('/').pop(), size_bytes: 1 })) }) as OrphanFoldersResponse;

beforeEach(() => {
	mockFetch.mockReset();
	mockDelete.mockReset();
	mockBulk.mockReset();
});

describe('OrphanFolders open', () => {
	it('opens, loads the folders and stops loading', async () => {
		mockFetch.mockResolvedValueOnce(response('/a'));
		const o = new OrphanFolders();
		const p = o.open();
		expect(o.isOpen).toBe(true);
		expect(o.loading).toBe(true);
		await p;
		expect(o.loading).toBe(false);
		expect(o.data).toEqual(response('/a'));
	});

	it('clears earlier feedback and selection', async () => {
		mockFetch.mockResolvedValue(response('/a'));
		const o = new OrphanFolders();
		o.feedback = { type: 'error', message: 'old' };
		o.toggle('/a');
		await o.open();
		expect(o.feedback).toBeNull();
		expect(o.selected.size).toBe(0);
	});

	it('sets the data to null when the fetch fails', async () => {
		mockFetch.mockResolvedValueOnce(response('/a'));
		const o = new OrphanFolders();
		await o.open();
		mockFetch.mockRejectedValueOnce(new Error('boom'));
		await o.open();
		expect(o.data).toBeNull();
		expect(o.loading).toBe(false);
		expect(o.isOpen).toBe(true);
	});
});

describe('OrphanFolders toggle', () => {
	it('selects then deselects a path', () => {
		const o = new OrphanFolders();
		o.toggle('/a');
		expect(o.selected.has('/a')).toBe(true);
		o.toggle('/a');
		expect(o.selected.has('/a')).toBe(false);
	});
});

describe('OrphanFolders deleteOne', () => {
	it('reports the last path segment, reloads and clears the selection', async () => {
		mockDelete.mockResolvedValueOnce(undefined as never);
		mockFetch.mockResolvedValueOnce(response('/x/y'));
		const o = new OrphanFolders();
		o.toggle('/x/z');
		const p = o.deleteOne('/x/z');
		expect(o.busy).toBe(true);
		await p;
		expect(mockDelete).toHaveBeenCalledWith('/x/z');
		expect(o.feedback).toEqual({ type: 'success', message: 'Folder "z" deleted' });
		expect(o.data).toEqual(response('/x/y'));
		expect(o.selected.size).toBe(0);
		expect(o.busy).toBe(false);
	});

	it('reports an Error message and clears busy', async () => {
		mockDelete.mockRejectedValueOnce(new Error('nope'));
		const o = new OrphanFolders();
		await o.deleteOne('/a');
		expect(o.feedback).toEqual({ type: 'error', message: 'nope' });
		expect(mockFetch).not.toHaveBeenCalled();
		expect(o.busy).toBe(false);
	});

	it('falls back to a generic message for a non-Error', async () => {
		mockDelete.mockRejectedValueOnce('x');
		const o = new OrphanFolders();
		await o.deleteOne('/a');
		expect(o.feedback).toEqual({ type: 'error', message: 'Delete failed' });
	});
});

describe('OrphanFolders deleteSelected', () => {
	it('sends the selection, reports the result and reloads', async () => {
		mockBulk.mockResolvedValueOnce({ removed: ['/a', '/b'], errors: [] } as never);
		mockFetch.mockResolvedValueOnce(response());
		const o = new OrphanFolders();
		o.toggle('/a');
		o.toggle('/b');
		const p = o.deleteSelected();
		expect(o.busy).toBe(true);
		await p;
		expect(mockBulk).toHaveBeenCalledWith(['/a', '/b']);
		expect(o.feedback?.type).toBe('success');
		expect(o.selected.size).toBe(0);
		expect(o.busy).toBe(false);
	});

	it('reports errors in the result', async () => {
		mockBulk.mockResolvedValueOnce({ removed: ['/a'], errors: [{ path: '/b' }] } as never);
		mockFetch.mockResolvedValueOnce(response());
		const o = new OrphanFolders();
		await o.deleteSelected();
		expect(o.feedback?.type).toBe('error');
	});

	it('reports a thrown Error and clears busy', async () => {
		mockBulk.mockRejectedValueOnce(new Error('bad'));
		const o = new OrphanFolders();
		await o.deleteSelected();
		expect(o.feedback).toEqual({ type: 'error', message: 'bad' });
		expect(o.busy).toBe(false);
	});

	it('falls back to a generic message for a non-Error', async () => {
		mockBulk.mockRejectedValueOnce('x');
		const o = new OrphanFolders();
		await o.deleteSelected();
		expect(o.feedback).toEqual({ type: 'error', message: 'Bulk delete failed' });
	});
});
