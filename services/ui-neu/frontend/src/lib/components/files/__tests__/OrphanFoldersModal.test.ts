import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { OrphanFoldersResponse } from '$lib/api/maintenance';

vi.mock('$lib/api/maintenance', () => ({
	fetchOrphanFolders: vi.fn(),
	deleteFolder: vi.fn(),
	bulkDeleteFolders: vi.fn()
}));

vi.mock('$lib/features', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/features')>();
	return { ...actual, features: { ...actual.features } };
});

import { fetchOrphanFolders, deleteFolder, bulkDeleteFolders } from '$lib/api/maintenance';
import { features } from '$lib/features';
import { OrphanFolders } from '$lib/stores/orphan-folders.svelte';
import OrphanFoldersModal from '../OrphanFoldersModal.svelte';

const mockFetch = vi.mocked(fetchOrphanFolders);
const mockDelete = vi.mocked(deleteFolder);
const mockBulk = vi.mocked(bulkDeleteFolders);

const listing = () =>
	({
		folders: [
			{ path: '/raw/a', name: 'a', size_bytes: 2048, category: 'raw' },
			{ path: '/done/b', name: 'b', size_bytes: 0, category: 'completed' }
		]
	}) as unknown as OrphanFoldersResponse;

function setup() {
	const orphans = new OrphanFolders();
	render(OrphanFoldersModal, { orphans });
	return orphans;
}

async function openWith(orphans: OrphanFolders, data: OrphanFoldersResponse | Error) {
	if (data instanceof Error) mockFetch.mockRejectedValueOnce(data);
	else mockFetch.mockResolvedValueOnce(data);
	await orphans.open();
	await tick();
}

afterEach(cleanup);

beforeEach(() => {
	mockFetch.mockReset();
	mockDelete.mockReset();
	mockBulk.mockReset();
	(features as { maintenance: boolean }).maintenance = true;
});

describe('OrphanFoldersModal', () => {
	it('renders nothing while closed', () => {
		setup();
		expect(screen.queryByText('Orphan Folders')).toBeNull();
	});

	it('renders nothing when maintenance is off, even if open', async () => {
		(features as { maintenance: boolean }).maintenance = false;
		const orphans = setup();
		await openWith(orphans, listing());
		expect(screen.queryByText('Orphan Folders')).toBeNull();
	});

	it('shows the loading spinner while the folders load', async () => {
		const orphans = setup();
		mockFetch.mockReturnValueOnce(new Promise(() => {}));
		void orphans.open();
		await tick();
		expect(screen.getByText('Orphan Folders')).toBeTruthy();
		expect(screen.getByText('Loading...')).toBeTruthy();
		expect(screen.queryByText('No orphan folders found')).toBeNull();
	});

	it('lists each folder with its size and category', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		expect(screen.getByText('a')).toBeTruthy();
		expect(screen.getByText('b')).toBeTruthy();
		expect(screen.getByText('raw').getAttribute('data-category')).toBe('raw');
		expect(screen.getByText('completed').getAttribute('data-category')).toBe('completed');
		expect(screen.getAllByTitle('Delete folder')).toHaveLength(2);
	});

	it('checks a row and toggles the selection on change', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes[0].checked).toBe(false);
		await fireEvent.click(boxes[0]);
		await tick();
		expect(orphans.selected.has('/raw/a')).toBe(true);
		expect(boxes[0].checked).toBe(true);
		expect(boxes[1].checked).toBe(false);
	});

	it('deletes one folder from its delete button', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		mockDelete.mockResolvedValueOnce(undefined as never);
		mockFetch.mockResolvedValueOnce(listing());
		await fireEvent.click(screen.getAllByTitle('Delete folder')[0]);
		await tick();
		expect(mockDelete).toHaveBeenCalledWith('/raw/a');
	});

	it('disables the checkboxes and delete buttons while busy', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		orphans.busy = true;
		await tick();
		for (const b of screen.getAllByRole('checkbox')) expect((b as HTMLInputElement).disabled).toBe(true);
		for (const b of screen.getAllByTitle('Delete folder')) expect((b as HTMLButtonElement).disabled).toBe(true);
	});

	it('shows the empty message when no folders are found', async () => {
		const orphans = setup();
		await openWith(orphans, { folders: [] } as unknown as OrphanFoldersResponse);
		expect(screen.getByText('No orphan folders found')).toBeTruthy();
	});

	it('shows the failed-to-load message when the fetch fails', async () => {
		const orphans = setup();
		await openWith(orphans, new Error('boom'));
		expect(screen.getByText('Failed to load orphan folders')).toBeTruthy();
	});

	it('shows success feedback with the success alert', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		orphans.feedback = { type: 'success', message: 'All good' };
		await tick();
		const alert = screen.getByText('All good');
		expect(alert.classList.contains('alert-success')).toBe(true);
		expect(alert.classList.contains('alert-danger')).toBe(false);
	});

	it('shows error feedback with the danger alert', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		orphans.feedback = { type: 'error', message: 'Nope' };
		await tick();
		const alert = screen.getByText('Nope');
		expect(alert.classList.contains('alert-danger')).toBe(true);
		expect(alert.classList.contains('alert-success')).toBe(false);
	});

	it('shows the bulk delete button only with a selection, and runs it', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		expect(screen.queryByText(/selected/)).toBeNull();
		orphans.toggle('/raw/a');
		await tick();
		mockBulk.mockResolvedValueOnce({ removed: ['/raw/a'], errors: [] } as never);
		mockFetch.mockResolvedValueOnce(listing());
		await fireEvent.click(screen.getByText('Delete 1 selected'));
		await tick();
		expect(mockBulk).toHaveBeenCalledWith(['/raw/a']);
	});

	it('closes from the backdrop', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		await fireEvent.click(screen.getByLabelText('Close dialog'));
		await tick();
		expect(orphans.isOpen).toBe(false);
		expect(screen.queryByText('Orphan Folders')).toBeNull();
	});

	it('closes from the Close button', async () => {
		const orphans = setup();
		await openWith(orphans, listing());
		await fireEvent.click(screen.getByText('Close'));
		await tick();
		expect(orphans.isOpen).toBe(false);
	});
});
