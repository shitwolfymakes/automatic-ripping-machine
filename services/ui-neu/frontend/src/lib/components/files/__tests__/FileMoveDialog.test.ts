import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { DirectoryListing, FileEntry } from '$lib/api/files';

vi.mock('$lib/api/files', () => ({ fetchRoots: vi.fn(), fetchDirectory: vi.fn() }));

import { fetchDirectory } from '$lib/api/files';
import { FilesBrowser } from '$lib/stores/files-browser.svelte';
import { MovePicker } from '$lib/stores/move-picker.svelte';
import FileMoveDialog from '../FileMoveDialog.svelte';

const mockDir = vi.mocked(fetchDirectory);

const dir = (name: string) => ({ name, type: 'directory' }) as FileEntry;
const listingOf = (entries: FileEntry[], extra: Partial<DirectoryListing> = {}) =>
	({ entries, ...extra }) as DirectoryListing;

function setup(subpath = 'src', selected = ['raw::a']) {
	const browser = new FilesBrowser();
	browser.current = { root: 'raw', subpath };
	browser.selectedKeys = new Set(selected);
	const picker = new MovePicker(browser);
	const onconfirm = vi.fn();
	const view = render(FileMoveDialog, { picker, count: selected.length, onconfirm });
	return { picker, onconfirm, view };
}

afterEach(cleanup);

beforeEach(() => {
	mockDir.mockReset();
});

describe('FileMoveDialog', () => {
	it('renders nothing while the picker is closed', () => {
		setup();
		expect(screen.queryByText('Browse to the destination folder')).toBeNull();
	});

	it('shows the spinner and no folder list while loading', async () => {
		const { picker } = setup();
		mockDir.mockReturnValueOnce(new Promise(() => {}));
		void picker.open();
		await tick();
		expect(screen.getByText('Browse to the destination folder')).toBeTruthy();
		expect(document.querySelector('.spin')).not.toBeNull();
		expect(screen.queryByText('No subfolders')).toBeNull();
		expect(screen.queryByText('..')).toBeNull();
	});

	it('shows the go-up row, the folders, the current badge and the singular heading', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x'), dir('y')], { parent_subpath: '' }));
		await picker.open();
		await tick();
		expect(screen.getByText('Move 1 item')).toBeTruthy();
		expect(screen.getByText('raw/src')).toBeTruthy();
		expect(screen.getByText('current')).toBeTruthy();
		expect(screen.getByText('..')).toBeTruthy();
		expect(screen.getByText('x')).toBeTruthy();
		expect(screen.getByText('y')).toBeTruthy();
		expect(screen.queryByText('No subfolders')).toBeNull();
	});

	it('shows No subfolders and hides go-up at the top of an empty root, with a plural heading', async () => {
		const { picker } = setup('', ['raw::a', 'raw::b']);
		mockDir.mockResolvedValueOnce(listingOf([]));
		await picker.open();
		await tick();
		expect(screen.getByText('Move 2 items')).toBeTruthy();
		expect(screen.getByText('No subfolders')).toBeTruthy();
		expect(screen.queryByText('..')).toBeNull();
	});

	it('loads a folder when its row is clicked and drops the badge and disabled state', async () => {
		const { picker, onconfirm } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')]));
		await picker.open();
		await tick();
		const move = screen.getByRole('button', { name: 'Move here' }) as HTMLButtonElement;
		expect(move.disabled).toBe(true);
		expect(move.title).toBe('Navigate to a different folder first');

		mockDir.mockResolvedValueOnce(listingOf([]));
		await fireEvent.click(screen.getByText('x'));
		await vi.waitFor(() => expect(screen.queryByText('current')).toBeNull());
		expect(mockDir).toHaveBeenLastCalledWith('raw', 'src/x');
		expect(screen.getByText('raw/src/x')).toBeTruthy();
		expect(move.disabled).toBe(false);
		expect(move.title).toBe('');
		await fireEvent.click(move);
		expect(onconfirm).toHaveBeenCalledTimes(1);
	});

	it('loads the parent folder when the go-up row is clicked', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValueOnce(listingOf([dir('x')], { parent_subpath: '' }));
		await picker.open();
		await tick();

		mockDir.mockResolvedValueOnce(listingOf([dir('src')]));
		await fireEvent.click(screen.getByText('..'));
		await vi.waitFor(() => expect(mockDir).toHaveBeenLastCalledWith('raw', ''));
		await vi.waitFor(() => expect(screen.getByText('src')).toBeTruthy());
		expect(picker.location).toEqual({ root: 'raw', subpath: '' });
	});

	it('closes from the backdrop and from Cancel', async () => {
		const { picker } = setup();
		mockDir.mockResolvedValue(listingOf([]));
		await picker.open();
		await tick();
		await fireEvent.click(screen.getByLabelText('Close dialog'));
		expect(picker.isOpen).toBe(false);
		await picker.open();
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(picker.isOpen).toBe(false);
	});
});
